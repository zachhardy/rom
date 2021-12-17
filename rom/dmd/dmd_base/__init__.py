import numpy as np
from numpy import ndarray

from numpy.linalg import svd
from numpy.linalg import norm

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes

from os.path import splitext
from typing import Union, List, Tuple

from pyPDEs.utilities import Vector

from pydmd.dmdbase import DMDBase as PyDMDBase


class DMDBase(PyDMDBase):
    """
    Dynamic Mode Decomposition base class inherited from PyDMD.

    Parameters
    ----------
    svd_rank : int or float, default 0
        The rank for the truncation. If 0, the method computes the
        optimal rank and uses it for truncation. If positive interger, the
        method uses the argument for the truncation. If float between 0 and 1,
        the rank is the number of the biggest singular values that are needed
        to reach the 'energy' specified by `svd_rank`. If -1, the method does
        not compute truncation.
    tlsq_rank : int, default 0
        Rank truncation computing Total Least Square. Default is 0,
        which means no truncation.
    exact : bool, default False
        Flag to compute either exact DMD or projected DMD.
    opt : bool or int, default False
        If True, amplitudes are computed like in optimized DMD  (see
        :func:`~dmdbase.DMDBase._compute_amplitudes` for reference). If
        False, amplitudes are computed following the standard algorithm. If
        `opt` is an integer, it is used as the (temporal) index of the snapshot
        used to compute DMD modes amplitudes (following the standard algorithm).
        The reconstruction will generally be better in time instants near the
        chosen snapshot; however increasing `opt` may lead to wrong results when
        the system presents small eigenvalues. For this reason a manual
        selection of the number of eigenvalues considered for the analyisis may
        be needed (check `svd_rank`). Also setting `svd_rank` to a value between
        0 and 1 may give better results.
    rescale_mode : {'auto'}, None, or ndarray, default None
        Scale Atilde as shown in 10.1016/j.jneumeth.2015.10.010 (section 2.4)
        before computing its eigendecomposition. None means no rescaling,
        'auto' means automatic rescaling using singular values, otherwise the
        scaling factors.
    forward_backward : bool, default False
        If True, the low-rank operator is computed
        like in fbDMD (reference: https://arxiv.org/abs/1507.02264).
    sorted_eigs : {'real', 'abs'} or False, default False
         Sort eigenvalues (and modes/dynamics accordingly) by
        magnitude if `sorted_eigs='abs'`, by real part (and then by imaginary
        part to break ties) if `sorted_eigs='real'`.
    """

    from ._plotting1d import plot_modes_1D, plot_snapshots_1D
    from ._plotting2d import plot_modes_2D, plot_snapshots_2D

    def __init__(self,
                 svd_rank: Union[int, float] = 0,
                 tlsq_rank: int = 0,
                 exact: bool = False,
                 opt: Union[bool, int] = False,
                 rescale_mode: Union[str, None, ndarray] = None,
                 forward_backward: bool = False,
                 sorted_eigs: Union[bool, str] = False) -> None:
        super().__init__(svd_rank, tlsq_rank, exact, opt,
                         rescale_mode, forward_backward, sorted_eigs)

        self._U: ndarray = None  # svd modes
        self._Sigma: ndarray = None  # singular values

    @property
    def n_snapshots(self) -> int:
        """
        Get the number of snapshots.

        Returns
        -------
        int
        """
        return self.snapshots.shape[1]

    @property
    def n_features(self) -> int:
        """
        Get the number of features in each snapshot.

        Returns
        -------
        int
        """
        return self.snapshots.shape[0]

    @property
    def n_modes(self) -> int:
        """
        Get the number of DMD modes in the expansion.

        Returns
        -------
        int
        """
        return self.modes.shape[1]

    @property
    def singular_values(self) -> ndarray:
        """
        Return the singular values of the snapshots.

        Returns
        -------
        ndarray (n_snapshots - 1,)
        """
        if self._Sigma is None:
            if self._snapshots is not None:
                _, self._Sigma, _ = svd(self._snapshots[:, :-1])
        return self._Sigma

    @property
    def svd_modes(self) -> ndarray:
        """
        Return the POD modes from the SVD column-wise.

        Returns
        -------
        ndarray (n_features, n_modes)
        """
        return self._U

    @property
    def reconstruction_error(self) -> float:
        """
        Compute the relative L^2 reconstruction error.

        Returns
        -------
        float
        """
        X: ndarray = self.snapshots
        Xdmd: ndarray = self.reconstructed_data
        return norm(X - Xdmd) / norm(X)

    @property
    def snapshot_reconstruction_errors(self) -> ndarray:
        """
        Compute the reconstruction error per snapshot.

        Returns
        -------
        ndarray (n_snapshots,)
        """
        X: ndarray = self.snapshots
        Xdmd: ndarray = self.reconstructed_data
        errors = np.empty(self.n_snapshots)
        for t in range(self.n_snapshots):
            errors[t] = norm(X[:, t] - Xdmd[:, t]) / norm(X[:, t])
        return errors

    def fit(self, X):
        """
        Abstract method to fit the snapshots matrices.

        Not implemented, it has to be implemented in subclasses.
        """
        raise NotImplementedError(
            'Subclass must implement abstract method {}.fit'.format(
                self.__class__.__name__))

    def plot_singular_values(self,
                             normalized: bool = True,
                             logscale: bool = True,
                             show_rank: bool = False,
                             filename: str = None) -> None:
        """
        Plot the singular value spectrum.

        Parameters
        ----------
        normalized : bool, default True
            Flag for normalizing the spectrum to its max value.
        logscale : bool, default True
            Flag for a log scale on the y-axis.
        show_rank : bool, default False
            Flag for showing the truncation location.
        filename : str, default None.
            A location to save the plot to, if specified.
        """
        # Format the singular values
        svals = self.singular_values
        if normalized:
            svals /= sum(svals)

        # Define the plotter
        plotter = plt.semilogy if logscale else plt.plot

        # Make figure
        plt.figure()
        plt.xlabel('n', fontsize=12)
        plt.ylabel('Singular Value' if not normalized
                   else 'Relative Singular Value')
        plotter(svals, '-*b')
        if show_rank:
            plt.axvline(self.n_modes - 1, color='r',
                        ymin=svals.min(), ymax=svals.max())
        plt.tight_layout()
        if filename is not None:
            base, ext = splitext(filename)
            plt.savefig(base + '.pdf')

    def plot_dynamics(self,
                      mode_indices: List[int] = None,
                      t: ndarray = None,
                      plot_imaginary: bool = False,
                      logscale: bool = False,
                      filename: str = None) -> None:
        # Check the inputs
        if self.modes is None:
            raise ValueError('The fit method must be performed first.')

        if t is None:
            t = np.arange(0, self.n_snapshots, 1)

        if self.n_snapshots // len(t) != 1:
            raise ValueError(
                'There must be the same number of times as snapshots.')

        if mode_indices is None:
            mode_indices = list(range(self.n_modes))
        elif isinstance(mode_indices, int):
            mode_indices = [mode_indices]

        # Plot each mode dynamic specified
        for idx in mode_indices:
            idx += 0 if idx > 0 else self.n_modes
            dynamic: ndarray = self.dynamics[idx] / self._b[idx]
            omega = np.log(self.eigs[idx]) / self.original_time['dt']

            # Make figure
            fig: Figure = plt.figure()
            # Make figure
            fig: Figure = plt.figure()
            fig.suptitle(f'DMD Dynamics {idx}\n$\omega$ = '
                         f'{omega.real:.3e}'
                         f'{omega.imag:+.3g}', fontsize=12)
            n_plots = 2 if plot_imaginary else 1

            # Plot real part
            real_ax: Axes = fig.add_subplot(1, n_plots, 1)
            real_ax.set_xlabel('r', fontsize=12)
            real_ax.set_ylabel('Real', fontsize=12)
            real_ax.grid(True)
            real_plotter = real_ax.semilogy if logscale else real_ax.plot
            real_plotter(t, dynamic.real)

            # Plot the imaginary part
            if plot_imaginary:
                imag_ax: Axes = fig.add_subplot(1, n_plots, 2)
                imag_ax.set_xlabel('t', fontsize=12)
                imag_ax.set_ylabel('Imaginary', fontsize=12)
                imag_ax.grid(True)
                imag_plotter = imag_ax.semilogy if logscale else imag_ax.plot
                imag_plotter(t, dynamic.imag)

            plt.tight_layout()
            if filename is not None:
                base, ext = splitext(filename)
                plt.savefig(base + f'_{idx}.pdf')

    @staticmethod
    def _format_subplots(n_plots: int) -> Tuple[int, int]:
        """
        Determine the number of rows and columns for subplots.

        Parameters
        ----------
        n_plots : int

        Returns
        -------
        int, int : n_rows, n_cols
        """
        if n_plots < 4:
            n_rows, n_cols = 1, n_plots
        elif 4 <= n_plots < 9:
            tmp = int(np.ceil(np.sqrt(n_plots)))
            n_rows = n_cols = tmp
            for n in range(1, n_cols + 1):
                if n * n_cols >= n_plots:
                    n_rows = n
                    break
        else:
            raise AssertionError('Maximum number of subplots is 9. '
                                 'Consider modifying the visualization.')
        return n_rows, n_cols
