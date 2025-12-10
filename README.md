# Lock Hog

A simple tool for hogging locks.

Code that utilizes concurrency is notoriously difficult to write tests for. `lock-hog` 
offers a utility to help with the testing of concurrent code that involves locks. The 
utility acquires the lock until instructed to release it (hogging the lock, if you 
will).

The package can be used to hog more than just the primitive locks that python provides 
(e.g. see [below](#acquiring-a-database-lock) for an example of how to hog a database 
lock).

## How it Works

The package offers a context manager `hog_lock`, which acquires a lock on entry and 
releases it on exit. The lock is acquired from within a different thread/process to the 
one that calls `hog_lock`. `hog_lock` can also be used as a decorator.

You will need to pass `hog_lock` a context manager that acquires and releases the lock 
you want to be hogged (see below for examples). A class, `LockHogger`, is provided, to 
help you write these context managers, but its usage is entirely optional.

An asynchronous utility is also provided, `async_hog_lock`, which operates in pretty 
much exact analogy to `hog_lock`.

## Examples

### Debouncing a Function

As a simple example, consider a function `pay_individual`, which we only want to be 
called by one thread at a time. If one thread calls the function whilst it is still 
being executed by another thread, we want an exception to be thrown. Implementing this 
could look something like:
~~~python
# inside pay_individual.py
import threading

def _pay_individual(...) -> None:
    # The actual implementation of pay_individual
    ...

class AlreadyPayingIndividual(Exception):
    pass

PAY_INDIVIDUAL_LOCK = threading.Lock()

def pay_individual(...) -> None:
    
    lock_acquired = PAY_INDIVIDUAL_LOCK.acquire(blocking=False)
    
    if not lock_acquired:
        raise AlreadyPayingIndividual
    
    _pay_individual(...)
    
    PAY_INDIVIDUAL_LOCK.release()

~~~

Say we wanted to write a test to verify that `AlreadyPayingIndividual` is raised when 
`pay_individual` is called but `PAY_INDIVIDUAL_LOCK` is acquired. Using `hog_lock` to do
so would look something like this:
~~~python
# inside test_pay_individual.py
import unittest

import lock_hog

import pay_individual

class PayIndividualLockHogger(lock_hog.LockHogger):
    def acquire_lock(self) -> None:
        pay_individual.PAY_INDIVIDUAL_LOCK.acquire()
    
    def release_lock(self) -> None:
        pay_individual.PAY_INDIVIDUAL_LOCK.release()

class TestPayIndividual(unittest.TestCase):
    def test_raises_if_multiple_threads_try_to_pay_individuals(self) -> None:
        with lock_hog.hog_lock(lock_hogger=PayIndividualLockHogger()):
            with self.assertRaises(pay_individual.AlreadyPayingIndividual):
                pay_individual.pay_individual(...)

~~~

Let's break down what happened in the above.
- First, we defined a subclass of `lock_hog.LockHogger` called 
    `PayIndividualLockHogger`, telling it how to acquire and release 
    `PAY_INDIVIDUAL_LOCK` by defining the methods `acquire_lock` and `release_lock` on
    it
- Then, we passed an instance of `PayIndividualLockHogger` to the `lock_hogger` argument
    of `lock_hog.hog_lock`
- When we entered `lock_hog.hog_lock`, it used the passed `PayIndividualLockHogger` 
    instance to acquire `PAY_INDIVIDUAL_LOCK`
- We then entered unittest's `assertRaises`
    [helper](https://docs.python.org/3/library/unittest.html#unittest.TestCase.assertRaises),
    so that our test can verify that `pay_individual` raises if called whilst 
    `PAY_INDIVIDUAL_LOCK` is acquired
- From within `assertRaises`, we call `pay_individual`, which raises 
    `AlreadyPayingIndividual` because `PAY_INDIVIDUAL_LOCK` has been acquired by
    `hog_lock`, and so we exit the `assertRaises` block without the test failing
- Finally, we exit `lock_hog.hog_lock`, which releases `PAY_INDIVIDUAL_LOCK` (so that no
    other tests are polluted by `PAY_INDIVIDUAL_LOCK` being acquired)

Because `hog_lock` can also be used as a decorator, we could also have written the test 
as such:

~~~python
class TestPayIndividual(unittest.TestCase):
    @lock_hog.hog_lock(lock_hogger=PayIndividualLockHogger())
    def test_raises_if_multiple_threads_try_to_pay_individuals(self) -> None:
        ...
~~~

#### Aside: `hog_lock` only cares about being handed a context manager

The class `lock_hog.LockHogger` is only really provided for convenience/code clarity. 
`hog_lock` would have accepted being passed any context manager. For example, we could 
have explicitly built a context manager that acquires/releases `PAY_INDIVIDUAL_LOCK`
ourselves by using the `__enter__` and `__exit__` dunder methods:

~~~python
# inside test_pay_individual.py
import types
import unittest

import lock_hog

import pay_individual

class PayIndividualLockHogger(lock_hog.LockHogger):
    def __enter__(self) -> None:
        pay_individual.PAY_INDIVIDUAL_LOCK.acquire()
    
    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception_value: BaseException | None,
        exception_traceback: types.TracebackType | None,
    ) -> None:
        pay_individual.PAY_INDIVIDUAL_LOCK.release()

class TestPayIndividual(unittest.TestCase):
    # as before
    ...

~~~

Taking this further, `threading.Lock` itself is a context manager, and so could have 
been passed directly to `lock_hogger` to achieve the same behaviour:

~~~python
# inside test_pay_individual.py
import unittest

import lock_hog

import pay_individual

class TestPayIndividual(unittest.TestCase):
    def test_raises_if_multiple_threads_try_to_pay_individuals(self) -> None:
        # `lock_hogger` does not have to be provided as a keyword argument
        with lock_hog.hog_lock(pay_individual.PAY_INDIVIDUAL_LOCK):
            with self.assertRaises(pay_individual.AlreadyPayingIndividual):
                pay_individual.pay_individual(...)

~~~

### Acquiring a Database Lock

Say we had some django code that only runs if it can acquire a lock:

~~~python
# inside pay_individual.py
import pglock

from django.db import transaction

def _pay_individual(...) -> None:
    # The actual implementation of pay_individual
    ...

class AlreadyPayingIndividual(Exception):
    pass

def _get_advisory_lock_name_for_pay_individual(
    *,
    individual: models.Individual,
) -> str:
    return f"pay-individual-{individual.id}"

def pay_individual(
    *,
    individual: models.Individual,
    ...,
) -> None:
    with transaction.atomic():
        lock_acquired = pglock.advisory(
            _get_advisory_lock_name_for_pay_individual(individual=individual),
            xact=True,
            timeout=0,
        ).acquire()
        
        if not lock_acquired:
            raise AlreadyPayingIndividual
        
        _pay_individual(...)

~~~

Testing this code in a single-threaded setting is non-trivial, as it's not
possible to open different database transactions from one thread using the utilities 
that django provides. `lock_hog` makes opening multiple database transactions and 
testing the advisory lock more straightforward:

~~~python
# inside test_pay_individual.py
import contextlib
import typing

import lock_hog
import pglock

from django.db import transaction, close_old_connections
from django.test import TestCase

import models
import pay_individual


def build_pay_individual_lock_hogger(
    self,
    *,
    individual: models.Individual,
) -> typing.Generator[None, None, None]:
    # define a lock hogger that acquires the advisory lock from a transaction opened in 
    # a different thread, then yields for other threads to resume operation
    @contextlib.contextmanager
    def pay_individual_lock_hogger():
        with transaction.atomic():
            pglock.advisory(
                pay_individual._get_advisory_lock_name_for_pay_individual(
                    individual=individual,
                ),
                xact=True,
                timeout=0,
            ).acquire()
            yield
        # close old connections, just to be safe/make sure our extra thread doesn't lead
        # to dangling connections
        close_old_connections()

    return pay_individual_lock_hogger

class TestPayIndividual(TestCase):
    def test_raises_individual_already_being_paid(self) -> None:
        individual = models.Individual.objects.create(...)
    
        pay_individual_lock_hogger = build_pay_individual_lock_hogger(
            individual=individual
        )
    
        with lock_hog.hog_lock(lock_hogger=pay_individual_lock_hogger):
            with self.assertRaises(pay_individual.AlreadyPayingIndividual):
                pay_individual.pay_individual(...)

~~~

Interestingly, this means you can test locking behaviours without having to use 
`TransactionTestCase` (because the transaction that acquires the lock is opened in a 
different thread to the one that is running the test).

This example was the real-world situation that prompted the writing of this package. 

### Other uses

This package should be useful wherever you need to acquire a lock from a different 
thread/process to the one running the test. As such, you could use it for hogging:
- Advisory locks in databases other than postgres (i.e. not using `pglock` as in the 
  above example)
- UNIX file/io locks, using `fcntl` (see 
  [docs](https://docs.python.org/3/library/fcntl.html))
- A distributed redis lock, using `redis.lock.Lock`

### Hogging async locks

Async variants of `hog_lock` and `LockHogger` are also provided (named `async_hog_lock`
and `AsyncLockHogger` respectively). Their API is very similar to their synchronous 
versions, albeit in an asynchronous form.

Say that `pay_individual` from the first example was actually an asynchronous function:
~~~python
# inside pay_individual.py
import asyncio

async def _pay_individual(...) -> None:
    # The actual implementation of pay_individual
    ...

class AlreadyPayingIndividual(Exception):
    pass

PAY_INDIVIDUAL_LOCK = asyncio.Lock()

async def pay_individual(...) -> None:
    try:
        async with asyncio.timeout(0.1):
            await PAY_INDIVIDUAL_LOCK.acquire()
    except asyncio.TimeoutError as e:
        raise AlreadyPayingIndividual from e
    
    await _pay_individual(...)
    
    PAY_INDIVIDUAL_LOCK.release()

~~~

Using `async_hog_lock` and `AsyncLockHogger` to test its behaviour may look something 
like:
~~~python
# inside test_pay_individual.py
import unittest

import lock_hog

import pay_individual

class PayIndividualLockHogger(lock_hog.AsyncLockHogger):
    async def acquire_lock(self) -> None:
        await pay_individual.PAY_INDIVIDUAL_LOCK.acquire()
    
    async def release_lock(self) -> None:
        pay_individual.PAY_INDIVIDUAL_LOCK.release()

class TestPayIndividual(unittest.IsolatedAsyncioTestCase):
    def test_raises_if_multiple_tasks_try_to_pay_individuals(self) -> None:
        with lock_hog.async_hog_lock(lock_hogger=PayIndividualLockHogger()):
            with self.assertRaises(pay_individual.AlreadyPayingIndividual):
                pay_individual.pay_individual(...)

~~~

## Contributing to `lock-hog`

### Running tests

Tests can be run from within the virtual environment using:
~~~bash
python3 -m unittest
~~~

Alternatively, tests can be run using `uv`:
~~~bash
uv run python3 -m unittest
~~~

Before running tests, you may need to run either:
~~~bash
python3 -m pip install -e .
~~~
or:
~~~bash
uv pip install -e .
~~~
in order to install `lock-hog` in development/editable mode (`uv` might have 
automatically done this for you).

Please ensure all PRs have appropriate test coverage.

## Avenues for Improvement

### Flesh Out README More

We should include an API reference for `hog_lock` and `LockHogger`. Mention `LockHogger`
provides no guarantees that any locks acquired in `acquire_lock` will be released.

### Add github actions

It'd be nice to have github actions to run both the test suite and `mypy` on `main` and 
pull requests.
