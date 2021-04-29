"""
Fittable Data Transformer
-------------------------
"""
from darts import TimeSeries
from typing import Union, Sequence, Callable, Iterator, Tuple
from darts.logging import get_logger
from darts.dataprocessing.transformers import BaseDataTransformer
from darts.utils import _parallel_apply, _build_tqdm_iterator

logger = get_logger(__name__)


class FittableDataTransformer(BaseDataTransformer):
    def __init__(self,
                 ts_transform: Callable,
                 ts_fit: Callable,
                 name: str = "FittableDataTransformer",
                 n_jobs: int = 1,
                 verbose: bool = False,
                 **kwargs):

        """
        Base class for fittable transformers offering both `transform()` and `fit()` methods.
        The fitting and transformation functions must be passed during the transformer's initialization. This class
        takes care of parallelizing both transformers fitting and transformation of multiple TimeSeries when possible.

        Parameters
        ----------
        ts_transform (Callable)
            Function that will be applied to each TimeSeries object once the `transform()` function is called. The
            function must take as first argument a TimeSeries object, and return the transformed TimeSeries object.
            Additional parameters can be added if necessary, but in this case, the `_transform_iterator()` should be
            redefined accordingly, to yeild the necessary arguments to this function (See `_transform_iterator()` for
            further details)
        ts_fit (Callable)
            Function that will be applied to each TimeSeries object once the `fit()` function is called.
            The function must take as first argument a TimeSeries object, and return an object containing information
            reagrding the fitting phase (e.g., parameters, or external transformers objects). All these parameters will
            be stored in self._fitted_params, which can be later used during the transformation step.

            Additional parameters can be added if necessary, but in this case, the `_fit_iterator()`
            should be redefined accordingly, to yeild the necessary arguments to this function (See
            `_inverse_transform_iterator()` for further details)
        name
            The data transformer's name
        n_jobs
            The number of jobs to run in parallel (in case the transformer is handling a Sequence[TimeSeries]).
            Defaults to `1` (sequential). `-1` means using all the available processors.
            Note: for small amount of data, the parallelization overhead could end up increasing the total
            required amount of time.
        verbose
            Optionally, whether to print operations progress
        """
        super().__init__(ts_transform=ts_transform,
                         name=name,
                         n_jobs=n_jobs,
                         verbose=verbose,
                         **kwargs)
        self._fit_called = False
        self.fitted_params = None  # stores the fitted parameters/objects
        self._ts_fit = ts_fit

    def _fit_iterator(self, series: Sequence[TimeSeries]) -> Iterator[Tuple]:
        """
        Returns an `Iterator` object with tuples of inputs for each single call to `ts_fit()`.
        Additional `args` and `kwargs` from `fit()` (that don't change across the calls to `ts_fit()`)
        are already forwarded, and thus don't need to be included in this generator.

        The basic implementation of this method returns `zip(series)`, that is, a generator of single-valued tuples,
        each containing one TimeSeries object.

        Parameters
        ----------
        series (Sequence[TimeSeries])
            Sequence of TimeSeries received in input.

        Returns
        -------
        (Iterator[Tuple])
            An iterator containing tuples of inputs for the `ts_fit()` method.

        Examples
        ________

        def my_ts_transform(series: TimeSeries, n: int) -> TimeSeries:
            return series + n

        def my_ts_fit(series: TimeSeries, m: float) -> TimeSeries:
            return max(series.first_value(), m)


        class IncreasingAdder(FittableDataTransformer):
            def __init__(self):
                super().__init__(ts_transform=my_ts_transform,
                                ts_fit=my_ts_fit)

            def _transform_iterator(self, series: Sequence[TimeSeries]) -> Iterator[Tuple[TimeSeries, float]]:
                # the increased quantity is the max between 0 and the first value in the series (stored into
                # self._fitted params)
                return zip(series, self._fitted_params)

            def _fit_iterator(self, series: Sequence[TimeSeries]) -> Iterator[Tuple[TimeSeries, int]]:
                # the second generator is setting the m parameter of my_ts_fit() to 0 for each TimeSeries
                return zip(series, (0 for i in range(len(series))))

        """
        return zip(series)

    def fit(self, series: Union[TimeSeries, Sequence[TimeSeries]], *args, **kwargs) -> 'FittableDataTransformer':
        """
        Fit the data and stores the fitting parameters into `self._fitted_params`. If a `Sequence` is passed as input
        data, this function takes care of parallelising the fitting of multiple series in the sequence at the same time
        (in this case 'self._fitted_params' will contain an array of fitted params, one for each TimeSeries).

        Parameters
        ----------
        series
            TimeSeries or Sequence of TimeSeries against which the transformer is fit.
        args
            Additional positional arguments for the `ts_fit()` method
        kwargs
            Additional keyword arguments for the `ts_fit()` method

        Returns
        -------
        FittableDataTransformer
            Fitted transformer.
        """
        self._fit_called = True

        desc = "Fitting ({})".format(self._name)

        if isinstance(series, TimeSeries):
            data = [series]
        else:
            data = series

        input_iterator = _build_tqdm_iterator(self._fit_iterator(data),
                                              verbose=self._verbose,
                                              desc=desc,
                                              total=len(data))

        self._fitted_params = _parallel_apply(input_iterator, self._ts_fit,
                                              self._n_jobs, args, kwargs)

        return self

    def fit_transform(self,
                      series: Union[TimeSeries, Sequence[TimeSeries]],
                      *args,
                      **kwargs) -> Union[TimeSeries, Sequence[TimeSeries]]:
        """
        Fit the transformer with the (Sequence of) TimeSeries and returns the transformed input

        Parameters
        ----------
       series
            TimeSeries or Sequence of TimeSeries to transform.
        args
            Additional positional arguments for the `ts_transform()` method
        kwargs
            Additional keyword arguments for the `ts_transform()` method

        Returns
        -------
        T
            Transformed data.
        """
        return self.fit(series).transform(series, *args, **kwargs)
