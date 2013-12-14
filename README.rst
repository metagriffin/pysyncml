=======================
Python SyncML Framework
=======================

Welcome to the ``pysyncml`` library, a pure-python implementation of
the SyncML adapter framework and protocol. SyncML_ is a protocol to
synchronize opaque objects between multiple clients and a
server. Although pysyncml does provide some utilities to synchronize
certain types of content and is therefore useful as-is, it is
primarily intended to be used as a library by other applications that
want to add data synchronization support via SyncML.

.. important::

  2012/09/16: pysyncml is currently beta. That means it has not had
  much "real-world" experience and you may encounter many
  bugs. However, it is being actively developed, so check back in a
  couple of months.

  If you decide to use it anyway, you are strongly encouraged to do a
  full backup of your data *before* you use pysyncml to synchronize
  production data.

  Working components as of 0.1.dev-r60:

  * Client-side SyncML framework with support for CRUD operations,
    i.e. Add/Replace/Delete Sync commands.

  * Server-side SyncML framework with support for CRUD operations,
    i.e. Add/Replace/Delete Sync commands.

  * Server-side conflict detection and multi-policy resolution.

  * Native support for "note" datatype.


Goals
=====

The pysyncml project has the following goals, some of them diverge
critically from other SyncML implementations and are the reasons for
creating a new package instead of building on other existing
implementations:

* Can be installed and used with a single "``pip install pysyncml``"
  (or easy_install).
* Is python 2.7+ and 3+ compatible.
* Implements a sufficiently large subset of the SyncML 1.2.2 (a.k.a.
  the OMA Data Synchronization specification) as to be interoperable
  with other implementations without necessarily being "conformant".
* Can be easily integrated into SQLAlchemy_ based projects to
  store data in the application's database instead of separated out
  (so that integrated database triggers and cascading can be applied).
* Can be extended in order to make properly crafted clients able
  to operate in "distributed" mode - this means that in the absence
  of a network, SyncML client peers are able to synchronize with
  each other in the anticipation that the central server may or may
  not eventually become available again.
* Differentiates as little as possible between "client" and "server"
  modes to enable the previous goal.
* Makes basic synchronization easy and complicated synchronization
  possible by providing standard implementations for commonly used
  approaches, while allowing these components to be overriden or
  extended.
* Provides basic command line tools for commonly synchronized data
  types.
* Provides a framework of server-push notifications which are
  transport agnostic.
* Auto-discovery of SyncML server URI locations; i.e. finding the
  "right" paths to bind object types is done automatically instead
  of needing error-prone user configuration.


Limitations
===========

It is the goal of the project to get a minimally functional library going
in the shortest possible timeframe. To that end, the following features
of SyncML will *NOT* be implemented until a later phase, even if this means
that the library does not provide a conformant implementation:

* NOT supported: filtering of searches or synchronization targets.
* NOT supported: data split over multiple messages.
* NOT supported: soft-deletes.
* NOT supported: memory constraint management.
* NOT supported: suspend, resume and busy signaling.
* NOT supported: MD5 authentication scheme.
* NOT supported: per-database-layer authorization.


Installation
============

Installation of pysyncml is near-trivial with PIP_:

.. code-block:: bash

  $ pip install pysyncml

or, using easy_install_:

.. code-block:: bash

  $ easy_install pysyncml


Pre-Requisites
==============

Python 2.7 or better is required, as the following is "taken for
granted" by the pysyncml developers:

* relative imports,
* "with" context manager statement,
* native ElementTree,
* ternary expression (EXPR if EXPR else EXPR),
* and something else which was found to not work in 2.6.4 but the
  author cannot remember what it was and does not wish to run into
  that limitation ever again...


Documentation
=============

For downloaded packages, please see the generated documents in the
"doc" directory, otherwise you can find links to the latest how-to and
API reference documentation at pysyncml_.

.. _SyncML: http://en.wikipedia.org/wiki/SyncML
.. _SQLAlchemy: http://www.sqlalchemy.org
.. _PIP: http://www.pip-installer.org
.. _easy_install: http://peak.telecommunity.com/DevCenter/EasyInstall
.. _pysyncml: http://www.pysyncml.org
