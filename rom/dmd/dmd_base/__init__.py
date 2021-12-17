import numpy as np
from numpy import ndarray
from numpy.linalg import norm
import matplotlib.pyplot as plt
from os.path import splitext
from scipy.linalg import pinv, svd
from typing import Union, Tuple, List

SVDRankType = Union[int, float]
SVDOutputType = Tuple[ndarray, ndarray, ndarray]
SortMethodType = Union[str, None]
RankErrorType = Tuple[ndarray, ndarray]
InputType = Union[ndarray, List[ndarray]]


class DMDBase:
    """
    Base class for Dynamic Mode Decomposition

    Parameters
    ----------
    svd_rank : int or float, default -1
        The SVD rank to use for truncation. If a positive integer,
        the minimum of this number and the maximum possible rank
        is used. If a float between 0 and 1, the minimum rank to
        achieve the specified energy content is used. If -1, no
        truncation is performed.
    exact : bool, default False
        A flag for using exact or projected dynamic modes.
    opt : bool, default False
        A flag for using optimal amplitudes or an initial
        condition fit.
    sort_method : str {'eigs', 'amps'} or Noneion fit.
        Mode sorting based on eigenvalues. If 'real', eigenvalues
        are sorted by their real part. If 'abs', eigenvalues are
        sorted by their magnitude. If None, no sorting is performed.
    """

    from ._plotting import plot_scree, plot_eigs
    from ._plotting import plot_modes_1D, plot_dynamics
    from ._plotting import plot_rankwise_errors, plot_timestep_errors

    def __init__(self,
                 svd_rank: SVDRankType = -1,
                 exact: bool = False,
                 opt: bool = False,
                 sort_method: str = None) -> None:

        # General parameters
        self._svd_rank: SVDRankType = svd_rank
        self._exact: bool = exact
        self._opt: bool = opt
        self._sort_method: str = sort_method

        # Snapshot information
        self._snapshots: ndarray = None
        self._snapshots_shape: Tuple[int, int] = None

        # Temporal information
        self.snapshot_time: dict = None
        self.dmd_time: dict = None

        # SVD structures
        self._U: ndarray = None
        self._Sigma: ndarray = None

        # DMD structures
        self._b: ndarray = None
        self._Atilde: ndarray = None
        self._eigenvectors: ndarray = None
        self._eigenvalues: ndarray = None
        self._modes: ndarray = None

    @property
    def svd_rank(self) -> SVDRankType:
        """
        Return the set SVD rank.

        Returns
        -------
        float or int
        """
        return self._svd_rank

    @property
    def exact(self) -> bool:
        """
        Return the flag for exact or projected modes.

        Returns
        -------
        bool
        """
        return self._exact

    @property
    def opt(self) -> bool:
        """
        Return the flag for optimized amplitudes.

        Returns
        -------
        bool
        """
        return self._opt

    @property
    def sort_method(self) -> str:
        """
        Get the eigenvalue sorting option.

        Returns
        -------
        str {'real', 'abs'}
        """
        return self._sort_method

    @property
    def snapshots(self) -> ndarray:
        """
        Get the snapshots.

        Returns
        -------
        ndarray (n_features, n_snapshots)
        """
        return self._snapshots

    @property
    def n_snapshots(self) -> int:
        """
        Get the number of snapshots.

        Returns
        -------
        int
        """
        return self._snapshots.shape[1]

    @property
    def n_features(self) -> int:
        """
        Get the number of features in each snapshot.

        Returns
        -------
        int
        """
        return self._snapshots.shape[0]

    @property
    def n_modes(self) -> float:
        """
        Get the number of modes in the expansion.

        Returns
        -------
        float
        """
        return self._modes.shape[1]

    @property
    def snapshot_timesteps(self) -> ndarray:
        """
        Get the snapshot timesteps for the problem.

        Returns
        -------
        ndarray (n_snapshots,)
        """
        t = np.arange(
            self.snapshot_time['t0'],
            self.snapshot_time['tf'] + self.snapshot_time['dt'],
            self.snapshot_time['dt'])
        return t[t <= self.snapshot_time['tf']]

    @property
    def dmd_timesteps(self) -> ndarray:
        """
        Get the DMD timesteps for the problem.

        Returns
        -------
        ndarray (varies,)
        """
        t = np.arange(
            self.dmd_time['t0'],
            self.dmd_time['tf'] + self.dmd_time['dt'],
            self.dmd_time['dt'])
        return t[t <= self.dmd_time['tf']]

    @property
    def svd_modes(self) -> ndarray:
        """
        Get the POD modes.

        Returns
        -------
        ndarray (n_features, rank)
        """
        return self._U

    @property
    def singular_values(self) -> ndarray:
        """
        Get the singular values.

        Returns
        -------
        ndarray (n_snapshots - 1,)
        """
        return self._Sigma

    @property
    def operator(self) -> ndarray:
        """
        Get the low-rank evolution operator.

        Returns
        -------
        ndarray (n_modes, n_modes)
        """
        return self._Atilde

    @property
    def eigenvalues(self) -> ndarray:
        """
        Get the eigenvalues of the evolution operator.

        Returns
        -------
        ndarray (n_modes,)
        """
        return self._eigenvalues

    @property
    def eigenvectors(self) -> ndarray:
        """
        Get the low-rank eigenvectors of the low-rank evolution operator.

        Returns
        -------
        ndarray (n_modes, n_modes)
        """
        return self._eigenvectors

    @property
    def amplitudes(self) -> ndarray:
        """
        Get the low-rank eigenvectors of the low-rank evolution operator.

        Returns
        -------
        ndarray (n_modes,)
        """
        return self._b

    @property
    def omegas(self) -> ndarray:
        """
        Get the continuous eigenvalues.

        Returns
        -------
        ndarray (rank,)
        """
        dt = self.snapshot_time['dt']
        return np.log(self.eigenvalues, dtype=complex) / dt

    @property
    def modes(self) -> ndarray:
        """
        Get the full-order DMD modes.

        Returns
        -------
        ndarray (n_features, n_modes)
        """
        return self._modes

    @property
    def dynamics(self) -> ndarray:
        """
        Return the dynamics operator.

        Returns
        -------
        ndarray (n_modes, n_snapshots)
        """
        t0, dt = self.snapshot_time['t0'], self.snapshot_time['dt']
        tmp = np.outer(self.eigenvalues, np.ones(self.dmd_timesteps.shape[0]))
        tpow = (self.dmd_timesteps - t0) / dt
        return np.power(tmp, tpow) * self._b[:, None]

    @property
    def reconstructed_data(self) -> ndarray:
        """
        Return the reconstructed data.

        Returns
        -------
        ndarray
        """
        return self.modes @ self.dynamics

    @property
    def reconstruction_error(self) -> float:
        """
        Compute the absolute reconstruction error.

        Returns
        -------
        float
        """
        X: ndarray = self.snapshots
        X_dmd: ndarray = self.reconstructed_data
        return norm(X - X_dmd) / norm(X)

    @property
    def timestep_errors(self) -> ndarray:
        """
        Get the reconstruction error per time step.

        Returns
        -------
        ndarray (n_snapshots,)
        """
        X: ndarray = self.snapshots
        Xdmd: ndarray = self.reconstructed_data

        errors = np.zeros(self.n_snapshots)
        for t in range(self.n_snapshots):
            errors[t] = norm(X[:, t] - Xdmd[:, t]) / norm(X[:, t])
        return errors

    def fit(self, X: InputType, verbose: bool) -> 'DMDBase':
        """
        Abstract method for fitting the DMD model.
        """
        raise NotImplementedError(
            f'{self.__class__.__name__} must implement the '
            f'`fit` method.')

    def _compute_svd(self, X: ndarray) -> SVDOutputType:
        """
        Compute the SVD of X.

        Parameters
        ----------
        X : ndarray (n_features, n_snapshots - 1)
            A snapshot matix.

        Returns
        -------
        U : ndarray (n_features, n_snapshots - 1)
            The left singular vectors, or POD modes.
        s : ndarray (n_snapshots - 1)
            The singular values.
        V : ndarray (n_snapshots - 1, n_snapshots - 1)
            The right singular vectors.
        """
        U, s, V = np.linalg.svd(X, full_matrices=False)
        V = V.conj().T

        svd_rank = self._svd_rank
        if 0 < svd_rank < 1:
            cumulative_energy = np.cumsum(s**2 / sum(s**2))
            rank = np.searchsorted(cumulative_energy, svd_rank) + 1
        elif svd_rank >= 1 and isinstance(svd_rank, int):
            rank = min(svd_rank, U.shape[1])
        else:
            rank = X.shape[1]

        self._Sigma = s
        self._U = U[:, :rank]
        return U[:, :rank], s[:rank], V[:, :rank]

    def _compute_operator(self, Y: ndarray, U: ndarray,
                          s: ndarray, V: ndarray) -> None:
        """
        Compute the low-rank evolution operator.

        Parameters
        ----------
        Y : ndarray (n_features, n_snapshots - 1)
            The front truncated snapshot matrix.
        U : ndarray (n_features, n_modes)
            The left singular vectors.
        s : ndarray (n_modes,)
            The singular values.
        V : ndarray (n_snapshots - 1, n_modes)
            The left singular vectors.
        """
        self._Atilde = U.conj().T @ Y @ V * np.reciprocal(s)

    def _decompose_Atilde(self) -> None:
        """
        Decompose the low-rank evolution operator.
        """
        # Compute decomposition
        eigvals, eigvecs = np.linalg.eig(self._Atilde)
        self._eigenvalues = eigvals
        self._eigenvectors = eigvecs

    def _compute_modes(self, Y: ndarray, U: ndarray,
                       s: ndarray, V: ndarray) -> None:
        """
        Compute the full-order DMD modes.

        Parameters
        ----------
        Y : ndarray (n_features, n_snapshots - 1)
            The front truncated snapshot matrix.
        U : ndarray (n_features, n_modes)
            The left singular vectors.
        s : ndarray (n_modes,)
            The singular values.
        V : ndarray (n_snapshots - 1, n_modes)
            The right singular vectors.
        """
        if not self.exact:
            self._modes = U @ self._eigenvectors
        else:
            inv_s = np.reciprocal(s)
            self._modes = Y @ V @ inv_s @ self._eigenvectors

    def _compute_amplitudes(self) -> ndarray:
        """
        Compute the amplitudes associated with each DMD mode.

        Returns
        -------
        ndarray (rank,)
        """
        if not self.opt:
            b = np.linalg.lstsq(
                self.modes, self.snapshots.T[0], rcond=None)[0]
        else:
            # Compute the Vandermonde matrix
            W, T = np.meshgrid(self.omegas, self.dmd_timesteps)
            vander: ndarray = np.exp(np.multiply(W, T)).T

            # Perform SVD on all the snapshots
            U, s, V = np.linalg.svd(self._snapshots, full_matrices=False)

            # Construct the LHS matrix
            PhiStar_Phi = self.modes.conj().T @ self.modes
            V_VStar_Conj = np.conj(vander @ vander.conj().T)
            P = PhiStar_Phi * V_VStar_Conj

            # Construct the RHS vector
            tmp = (U @ np.diag(s) @ V).conj().T
            q = np.diag(vander @ tmp @ self.modes).conj()

            # Solve Pb = q
            b = np.linalg.solve(P, q)

        # Enforce positive amplitudes
        for i in range(len(b)):
            if b[i].real < 0.0:
                b[i] *= -1.0
                self.modes.T[i] *= -1.0
        return b

    def _sort_modes(self) -> None:
        """
        Sort the modes based on sort method.
        """
        if self._sort_method in ['eigs', 'amps']:
            if self._sort_method == 'eigs':
                ind = np.argsort(self._eigenvalues.real)[::-1]
            else:
                ind = np.argsort(self._b.real)[::-1]
            self._eigenvalues = self._eigenvalues[ind]
            self._eigenvectors = self._eigenvectors.T[ind].T
            self._modes = self._modes.T[ind].T
            self._b = self._b[ind]

    def compute_rankwise_errors(self,
                                skip: int = 1,
                                end: int = -1) -> RankErrorType:
        """
        Compute the error as a function of rank.

        Parameters
        ----------
        skip : int, default 1
            Interval between ranks to compute errors for. The default
            is to compute errors at all ranks.
        end : int, default -1
            The last rank to compute the error for. The default is to
            end at the maximum rank.

        Returns
        -------
        ndarray (varies,)
            The ranks used to compute errors.
        ndarray (varies,)
            The errors for each rank.
        """
        X: ndarray = self._snapshots
        orig_rank = self._svd_rank
        if end == -1 or end > min(X.shape) - 1:
            end = min(X.shape) - 1

        # Compute errors
        errors, ranks = [], []
        for r in range(0, end, skip):
            self._svd_rank = r + 1
            self.fit(X, False)

            error = self.reconstruction_error.real
            errors.append(error)
            ranks.append(r)

        # Reset the model
        self._svd_rank = orig_rank
        self.fit(X, False)
        return ranks, errors

    def get_parameters(self) -> dict:
        """
        Get the model parameters from this model.

        Returns
        -------
        dict
        """
        return {'svd_rank': self._svd_rank, 'exact': self._exact,
                'opt': self._opt, 'sorted_eigs': self._sort_method}

    @staticmethod
    def _validate_data(X: InputType) -> Tuple[ndarray, Tuple[int, int]]:
        """
        Validate the training data.

        Parameters
        ----------
        X : ndarray or List[ndarray]
            The training snapshots.

        Returns
        -------
        ndarray (n_features, n_snapshots)
            The formatted snapshots.
        Tuple[int, int]
            The training snapshot shape.
        """
        if isinstance(X, ndarray) and X.ndim == 2:
            snapshots = X
            snapshots_shape = None
        else:
            input_shapes = [np.asarray(x).shape for x in X]

            if len(set(input_shapes)) != 1:
                raise ValueError(
                    'All snapshots must have the same dimension.')

            snapshots_shape = input_shapes[0]
            snapshots = np.transpose([np.array(x).flatten() for x in X])
        return snapshots, snapshots_shape
