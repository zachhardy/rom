import os
import numpy as np
import matplotlib.pyplot as plt

from numpy.linalg import norm
from numpy.linalg import svd
from numpy.linalg import eig
from numpy.linalg import multi_dot

from typing import Union, Optional
from collections.abc import Iterable

from ..rom_base import ROMBase
from ..utils import format_2darray

SVDRank = Union[int, float]
Snapshots = Union[np.ndarray, Iterable]
Indices = Components = Union[int, Iterable[int]]


class DMD(ROMBase):
    """
    Implementation of the dynamic mode decomposition.
    """

    plt.rcParams['text.usetex'] = True
    plt.rcParams['font.size'] = 12

    def __init__(
            self,
            svd_rank: SVDRank = 0,
            exact: bool = False,
            opt: bool = False,
            sorted_eigs: Optional[str] = None
    ) -> None:
        """
        Parameters
        ----------
        svd_rank : int or float, default 0
            The rank for mode truncation. If 0, use the optimal rank.
            If a float in (0.0, 0.5], use the rank corresponding to the
            number of singular values whose relative values are greater
            than the argument. If a float in (0.5, 1.0), use the minimum
            number of modes such that the energy content is greater than
            the argument. If a positive integer, use that rank.
        exact : bool, default False
            A flag for exact or projected modes.
        opt : bool, default False
            If True, compute optimal amplitudes with respect to all
            snapshots. If False, compute amplitudes via a fit to the
            initial condition.
        sorted_eigs : {'real', 'abs'} or None, default None
            Sort the modes by eigenvalue. If 'real', modes are sorted
            based on the real component of the eigenvalues. If 'abs',
            modes are sorted based on their magnitude. If None, no
            sorting is done.
        """
        self._svd_rank = svd_rank
        self._exact: bool = exact
        self._opt: bool = opt
        self._sorted_eigs: str = sorted_eigs

        # DMD data
        self._Atilde: np.ndarray = None

        self._eigvals: np.ndarray = None
        self._eigvecs: np.ndarray = None
        self._modes: np.ndarray = None

        self.original_time: dict = {}
        self.dmd_time: dict = {}

    @property
    def exact(self) -> bool:
        """
        Return the exact modes flag.

        Returns
        -------
        bool
        """
        return self._exact

    @property
    def opt(self) -> bool:
        """
        Return the optimized amplitudes flag.

        Returns
        -------
        bool
        """
        return self._opt

    @property
    def sorted_eigs(self) -> str:
        """
        Return the sorting method.

        Returns
        -------
        str
        """
        return self._sorted_eigs

    @property
    def modes(self) -> np.ndarray:
        """
        Return the DMD modes stored column-wise.

        Returns
        -------
        numpy.ndarray (n_features, n_modes)
        """
        return self._modes

    @property
    def Atilde(self) -> np.ndarray:
        """
        Return the reduced-rank evolution operator.

        Returns
        -------
        numpy.ndarray (n_modes, n_modes)
        """
        return self._Atilde

    @property
    def eigvals(self) -> np.ndarray:
        """
        Return the eigenvalues of Atilde

        Returns
        -------
        numpy.ndarray (n_modes,)
        """
        return self._eigvals

    @property
    def omegas(self) -> np.ndarray:
        """
        Return the continuous eigenvalus of the DMD modes.

        Returns
        -------
        numpy.ndarray (n_modes,)
        """
        w = np.log(self._eigvals) / self.original_time["dt"]
        for i in range(len(w)):
            if w[i].imag % np.pi < 1.0e-12:
                w[i] = w[i].real + 0.0j
        return w

    @property
    def frequency(self) -> np.ndarray:
        """
        Return the frequencies of the DMD mode eigenvalues.

        Returns
        -------
        numpy.ndarray (n_modes,)
        """
        return self.omegas.imag / (2.0 * np.pi)

    @property
    def eigvecs(self) -> np.ndarray:
        """
        Return the eigenvectors of Atilde, column-wise.

        Returns
        -------
        numpy.ndarray (n_modes, n_modes)
        """
        return np.transpose(self._eigvecs)

    @property
    def dynamics(self) -> np.ndarray:
        """
        Return the time evolution of each mode.

        Returns
        -------
        numpy.ndarray (n_modes, *)
        """
        # form the base dynamics matrix (n_modes, *)
        base = np.repeat(self._eigvals[:, None],
                         self.dmd_timesteps.shape[0],
                         axis=1)

        # each column is the eigenvalue raised to a power
        # - when dmd_timesteps = original_timesteps, this reduces to
        # - integer powers, however, when they are different, map the
        # - dmd time steps back to original time start and divide by
        # - the original time step. For example, when time step is
        # - halved this results to powers in increments of 0.5.
        powers = np.divide(self.dmd_timesteps - self.original_time["t0"],
                           self.original_time["dt"])

        # raise the base matrix to the specified powers and scale by
        # the associated amplitudes
        return np.power(base, powers) * self._b[:, None]

    @property
    def original_timesteps(self) -> np.ndarray:
        """
        Return the original time steps.

        Returns
        -------
        numpy.ndarray (n_snapshots,)
        """
        return np.arange(
            self.original_time["t0"],
            self.original_time["tend"] + self.original_time["tend"],
            self.original_time["dt"]
        )

    @property
    def dmd_timesteps(self) -> np.ndarray:
        """
        Return the DMD timesteps.

        Returns
        -------
        numpy.ndarray (*,)
        """
        return np.arange(
            self.dmd_time["t0"],
            self.dmd_time["tend"] + self.dmd_time["dt"],
            self.dmd_time["dt"]
        )

    @property
    def reconstructed_data(self) -> np.ndarray:
        """
        Return the reconstructed training data.

        Returns
        -------
        numpy.ndarray (n_features, n_snapshots)
        """
        return self._modes @ self.dynamics

    def fit(self, X: Snapshots) -> 'DMD':
        """
        Fit the DMD model to input snapshots X.

        Parameters
        ----------
        X : numpy.ndarray or Iterable
            The training snapshots.

        Returns
        -------
        DMD
        """
        X, Xshape = format_2darray(X)

        self._snapshots = X
        self._snapshots_shape = Xshape

        # Define the default time steps
        if not self.original_time:
            tend = self.n_snapshots - 1
            self.original_time = {"t0": 0, "tend": tend, "dt": 1}

        # Default DMD time steps are the same as original
        self.dmd_time = self.original_time.copy()

        # Peform the SVD
        self._U, self._s, self._Vstar = svd(X[:, :-1], False)
        self._rank = self._compute_rank(self._svd_rank)

        # Compute and decompose the low-rank evolution operator
        self._Atilde = self._compute_atilde()
        self._decompose_atilde()

        # Compute the high-dimensional modes
        self._compute_modes()

        # Compute the amplitudes
        self._b = self._compute_amplitudes()

        return self

    def refit(
            self,
            svd_rank: SVDRank,
            exact: bool = False,
            opt: bool = False
    ) -> 'DMD':
        """
        Re-fit the DMD model with the specified hyper-parameters.

        Parameters
        ----------
        svd_rank : int or float, default 0
            The rank for mode truncation. If 0, use the optimal rank.
            If a postive integer, use that rank. If a float between 0
            and 1, use all modes with singular values greater than
            the argument. If -1, do not truncate.
        exact : bool, default False
            A flag for exact or projected modes.
        opt : bool, default False
            If True, compute optimal amplitudes with respect to all
            snapshots. If False, compute amplitudes via a fit to the
            initial condition.

        Returns
        -------
        DMD
        """
        self._svd_rank = svd_rank
        self._exact = exact
        self._opt = opt

        # Recompute the rank
        self._rank = self._compute_rank(self._svd_rank)

        # Redo the algorithm after the SVD
        self._Atilde = self._compute_atilde()
        self._decompose_atilde()
        self._compute_modes()
        self._b = self._compute_amplitudes()

        return self

    def set_time_dict(self, value: dict) -> None:
        """
        Set the original time dictionary for the training snapshots.

        This routine resets the DMD time dictionary to the specified value.

        Parameters
        ----------
        value : dict
        """
        keys = set(value.keys())
        if keys != {"t0", "tend", "dt"}:
            raise KeyError("Invalid time dictionary provided.")

        self.original_time = value.copy()
        self.dmd_time = value.copy()

    def optimize_hyperparameters(self, verbose: bool = False) -> None:
        """
        Perform a parameter search for the optimal hyper-parameters.
        """
        import itertools

        ranks = list(range(1, self.n_snapshots))
        flags = [[False, True], [False, True]]
        cases = list(itertools.product(ranks, *flags))

        # Loop over each set
        if verbose:
            print("\nBeginning hyper-parameter optimization...")

        errors = []
        for rank, exact, opt in cases:
            self.refit(rank, exact, opt)
            errors.append(self.reconstruction_error)

        argmin = np.nanargmin(errors)
        self._svd_rank, self._exact, self._opt = cases[argmin]
        self.refit(*cases[argmin])

        if verbose:
            print(f"Hyper-parameter optimization completed.")
            print("Optimal Parameters:")
            print(f"\t{'# of Modes':<20}: {self._svd_rank}")
            print(f"\t{'Exact':<20}: {self._exact}")
            print(f"\t{'Opt':<20}: {self._opt}")

    def print_summary(self) -> None:
        """
        Print a summary of the DMD model.
        """
        print()
        print("=======================")
        print("===== DMD Summary =====")
        print("=======================")
        print(f"{'# of Modes':<20}: {self.n_modes}")
        print(f"{'# of Snapshots':<20}: {self.n_snapshots}")
        print(f"{'Reconstruction Error':<20}: "
              f"{self.reconstruction_error:.3g}")
        print(f"{'Mean Snapshot Error':<20}: "
              f"{np.mean(self.snapshot_errors):.3g}")
        print(f"{'Max Snapshot Error':<20}: "
              f"{np.max(self.snapshot_errors):.3g}\n")

    def _compute_atilde(self) -> np.ndarray:
        """
        Compute the low-rank evolution operator.

        Returns
        -------
        numpy.ndarray (n_modes, n_modes)
        """
        Y = self._snapshots[:, 1:]
        Ustar = self._U[:, :self._rank].conj().T
        V = self._Vstar[:self._rank].conj().T
        s_inv = np.reciprocal(self._s[:self._rank])
        return multi_dot([Ustar, Y, V]) * s_inv

    def _decompose_atilde(self) -> None:
        """
        Compute the eigendecomposition of the low-rank evolution operator.
        """

        # compute the eigendecomposition
        evals, evecs = eig(self._Atilde)
        self._eigvals = np.array(evals, complex)
        self._eigvecs = np.array(evecs, complex)

        # sorting
        if self._sorted_eigs is not None:

            # define the sort routine
            if self._sorted_eigs == 'abs':
                def k(tp):
                    return abs(tp[0])
            elif self._sorted_eigs == 'real':
                def k(tp):
                    e = tp[0]
                    if isinstance(e, complex):
                        return e.real, e.imag
                    return e.real, 0.0
            else:
                raise AssertionError(f"Unrecognized sorted_eigs value.")

            # perform the sort
            pairs = zip(self._eigvals, self._eigvecs.T)
            a, b = zip(*sorted(pairs, key=k)[::-1])
            self._eigvals = np.array([e for e in a])
            self._eigvecs = np.array([e for e in b]).T

    def _compute_modes(self) -> None:
        """
        Compute the high-dimensional dynamic modes.
        """

        if self._exact:
            Y = self._snapshots[:, 1:]
            V = self._Vstar[:self._rank].conj().T
            s_inv = np.reciprocal(self._s[:self._rank])
            self._modes = Y.dot(V) * s_inv.dot(self._eigvecs)

        else:
            U = self._U[:, :self._rank]
            self._modes = U.dot(self._eigvecs)

    def _compute_amplitudes(self) -> np.ndarray:
        """
        Compute the amplitudes for each DMD mode.

        Returns
        -------
        numpy.ndarray (n_modes,)
        """
        # optimized amplitudes
        if self._opt:

            # vandermonde matrix
            vander = np.vander(self._eigvals, len(self.dmd_timesteps), True)

            # form system to solve
            P = np.multiply(
                np.dot(self._modes.conj().T, self._modes),
                np.conj(np.dot(vander, vander.conj().T)),
            )

            q = np.conj(np.diag(multi_dot(
                [vander, self._snapshots.conj().T, self.modes]
            )))

            # solve system
            return np.linalg.solve(P, q)

        # fit modes to first snapshot
        else:
            return np.linalg.lstsq(
                self._modes, self._snapshots[:, 0], rcond=None
            )[0]

    def plot_dynamics(
            self,
            mode_indices: Optional[Indices] = None,
            logscale: bool = False,
            normalized: bool = True,
            filename: Optional[str] = None
    ) -> None:
        """
        Plot the dynamic behaviors of the modes at the DMD time steps.

        Parameters
        ----------
        mode_indices : int or Iterable[int], default None
            The indices of the modes to plot. The default behavior
            is to plot all modes.
        logscale : bool, default False
            A flag for a logarithmic y-axis.
        normalized : bool, default True
            Normalize the dynamic behaviors to unity at initial time.
        filename : str, default None
            A location to save the plot to, if specified.
        """

        ##################################################
        # Check inputs
        ##################################################

        if self.modes is None:
            cls_name = self.__class__.__name__
            msg = f"{cls_name} ROM has not been fit to data."
            raise ValueError(msg)

        # Check mode
        if mode_indices is None:
            mode_indices = list(range(self.n_modes))
        elif isinstance(mode_indices, int):
            mode_indices = [mode_indices]
        else:
            for idx in mode_indices:
                if idx < 0 or idx >= self.n_modes:
                    msg = "Invalid mode index encountered."
                    raise ValueError(msg)

        ##################################################
        # Plot the dynamics
        ##################################################

        plt.figure()
        plt.title("DMD Dynamics")
        plt.xlabel("Time")
        for idx in mode_indices:
            dynamic = self.dynamics[idx]
            if normalized:
                dynamic /= self._b[idx]

            omega = self.omegas[idx]
            plotter = plt.semilogy if logscale else plt.plot
            label = f"Mode {idx}, $\omega$={omega.real:.3e}{omega.imag:+.3e}j"
            plotter(self.dmd_timesteps, dynamic.real, label=label)

        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        if filename is not None:
            base, ext = os.path.splitext(filename)
            plt.savefig(f"{base}.pdf")
