# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/04/21
# copy: (C) Copyright 2012-EOT metagriffin -- see LICENSE.txt
#------------------------------------------------------------------------------
# This software is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This software is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see http://www.gnu.org/licenses/.
#------------------------------------------------------------------------------

'''
This module defines the abstract interface :class:`pysyncml.Agent
<pysyncml.agents.base.Agent>`, the base class for all pysyncml
synchronization agents.
'''

import sys, json, six
import xml.etree.ElementTree as ET
from ..common import ConflictError

#------------------------------------------------------------------------------
class Agent(object):
  '''
  The ``Agent`` interface is how the pysyncml Adapter interacts with
  the actual objects being synchronized.  The data is expected to be
  stored by the calling framework, and pysyncml manages the protocol
  for synchronization. This API defines the core required methods that
  need to be implemented (:meth:`addItem`, :meth:`getItem`,
  :meth:`replaceItem`, :meth:`deleteItem`, :meth:`getAllItems`,
  :meth:`loadItem`, :meth:`dumpItem`), as well as several optional
  methods that can be implemented for optimization purposes.

  Hierarchical Item Support

  To enable hierarchical item support for an Agent, set the attribute
  (or constructor parameter) `hierarchicalSync` to true. This will
  then cause pysyncml to process parent/child relationships. Note,
  however, that pysyncml does NOT enforce any kind of integrity
  checking. Specifically, pysyncml:

  * does NOT enforce a single parentless (i.e. root) item.
  * does NOT enforce that children are deleted before their
    parents.
  * does NOT detect or resolve orphaned children.

  These are all circumstances that are handled differently based on
  what kind of parent/child relationship exists, and is therefore
  outside of the scope of pysyncml to enforce.
  '''

  #----------------------------------------------------------------------------
  def __init__(self, contentTypes=None, hierarchicalSync=False, *args, **kw):
    super(Agent, self).__init__(*args, **kw)
    self.contentTypes     = contentTypes
    self.hierarchicalSync = hierarchicalSync

  #----------------------------------------------------------------------------
  # helper methods
  #----------------------------------------------------------------------------
  def deleteAllItems(self):
    '''
    [OPTIONAL] Deletes all items stored by this Agent. The default
    implementation simply iterates over :meth:`getAllItems` and
    deletes them one at a time.
    '''
    for item in self.getAllItems():
      self.deleteItem(item.id)

  #============================================================================
  # serialization methods -- these MUST be implemented
  #============================================================================

  # TODO: ideally, both would be implemented to call each other, but a
  #       trap for Recursion depth exception would be set so that i can
  #       warn about that... that would allow the sub-classer to implement
  #       either. the `(dump|load)*s*Item` should probably be the "optimized"
  #       route... ie. the non-string version should do the recursion check.

  #----------------------------------------------------------------------------
  def dumpItem(self, item, stream, contentType=None, version=None):
    '''
    Converts the specified `item` to serialized form (such that it can
    transported over the wire) and writes it to the provided file-like
    `stream` object. For agents that support multiple content-types,
    the desired `contentType` and `version` will be specified as a
    parameter. If `contentType` and `version` are None, appropriate
    default values should be used. For agents that concurrently use
    multiple content-types, the return value may be a two-element
    tuple of (contentType, version), thus overriding or enhancing the
    provided values.
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  def dumpsItem(self, item, contentType=None, version=None):
    '''
    [OPTIONAL] Identical to :meth:`dump`, except the serialized form
    is returned as a string representation. As documented in
    :meth:`dump`, the return value can optionally be a three-element
    tuple of (contentType, version, data) if the provided content-type
    should be overridden or enhanced. The default implementation just
    wraps :meth:`dump`.
    '''
    buf = six.StringIO()
    ret = self.dumpItem(item, buf, contentType, version)
    if ret is None:
      return buf.getvalue()
    return (ret[0], ret[1], buf.getvalue())

  #----------------------------------------------------------------------------
  def loadItem(self, stream, contentType=None, version=None):
    '''
    Reverses the effects of the :meth:`dumpItem` method, and returns
    the de-serialized Item from the file-like source `stream`.

    Note: `version` will typically be ``None``, so it should either be
    auto-determined, or not used. This is an issue in the SyncML
    protocol, and is only here for symmetry with :meth:`dumpItem`
    and as "future-proofing".
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  def loadsItem(self, data, contentType=None, version=None):
    '''
    [OPTIONAL] Identical to :meth:`loadItem`, except the serialized
    form is provided as a string representation in `data` instead of
    as a stream. The default implementation just wraps
    :meth:`loadItem`.
    '''
    buf = six.StringIO(data)
    return self.loadItem(buf, contentType, version)

  #============================================================================
  # core syncing methods -- these MUST be implemented
  #============================================================================

  #----------------------------------------------------------------------------
  def getAllItems(self):
    '''
    Returns an iterable of all the items stored in the local datastore.
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  def addItem(self, item):
    '''
    The specified `item`, which will have been created via a prior
    ``loadItem()``, is added to the local datastore. This method
    returns either a new :class:`pysyncml.Item
    <pysyncml.items.base.Item>` instance or the same `item` that was
    passed --- in either case, the returned item **MUST** have a valid
    :attr:`pysyncml.Item.id <pysyncml.items.base.Item.id>` attribute.
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  def getItem(self, itemID):
    '''
    Returns the :class:`pysyncml.Item <pysyncml.items.base.Item>`
    instance associated with the specified `itemID`, which may or may
    not have been converted to a string.
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  def replaceItem(self, item, reportChanges):
    '''
    Updates the local datastore item with ID `item.id` to the value
    provided as `item`, which will have been created via a prior
    ``loadItem()``.

    If `reportChanges` is True, then the return value will be used to
    track the changes that were applied. If `reportChanges` is True but
    ``None`` is returned, then change tracking will be disabled for
    this change, which will cascade to any past or future changes that
    have not yet been synchronized. The return value must be a string
    (or an object that supports coercion via ``str()``). If multiple
    changes accumulate for an object, they will be concatenated, in
    order, and delimited via a semicolon (";"). See :doc:`../merging`
    for details.
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  def deleteItem(self, itemID):
    '''
    Deletes the local datastore item with ID `itemID`.
    '''
    raise NotImplementedError()

  #============================================================================
  # extended syncing methods -- these SHOULD be implemented
  #============================================================================

  #----------------------------------------------------------------------------
  def matchItem(self, item):
    '''
    [OPTIONAL] Attempts to find the specified item and returns an item
    that describes the same object although it's specific properties
    may be different. For example, a contact whose name is an
    identical match, but whose telephone number has changed would
    return the matched item. ``None`` should be returned if no match
    is found, otherwise the item that `item` matched should be
    returned.

    This is used primarily when a slow-sync is invoked and objects
    that exist in both peers should not be replicated.

    Note that **NO** merging of the items' properties should be done;
    that will be initiated via a separate call to :meth:`mergeItems`.

    This method by default will iterate over all items (by calling
    :meth:`getAllItems`) and compare them using ``cmp()``. This means
    that if the items managed by this agent implement the ``__eq__``
    or ``__cmp__`` methods, then matching items will be detected and
    returned. Otherwise, any items that exist in both peers will be
    duplicated on slow-sync.

    Sub-classes *should* implement a more efficient method of finding
    matching items.

    See :doc:`../merging` for details.
    '''
    for match in self.getAllItems():
      if cmp(match, item) == 0:
        return match
    return None

  #----------------------------------------------------------------------------
  def mergeItems(self, localItem, remoteItem, changeSpec):
    '''
    [OPTIONAL] Merges the properties of `remoteItem`, which is an item
    provided by a remote peer during a synchronization, into the
    `localItem`, which is an item retrieved from this agent either via
    :meth:`getItem` or :meth:`matchItem`. `changeSpec` will represent
    the changes applied to `localItem` since `remoteItem` was last
    synchronized, or will be ``None`` when called as a result of a
    slow-sync :meth:`matchItem` call.

    This method should return a new change-spec (see
    :meth:`replaceItem` for details) that represents the changes
    applied to `localItem` from `remoteItem`.

    If the items cannot be merged, then a `pysyncml.ConflictError`
    should be raised with more descriptive information on what failed
    during the merge --- in which case pysyncml will revert to the
    conflict resolution policy defined by `store.conflictPolicy` or
    `adapter.conflictPolicy`.

    IMPORTANT: if the merge fails, `localItem` and `remoteItem` must
    stay untouched by this call; most importantly, if the merge fails
    with a ConflictError, then `remoteItem` must be in the identical
    state as when it entered the call.

    This method by default raises a ConflictError, which means that if
    any changes are made to the same item simultaneously by two
    different peers, they will result in a conflict and will not be
    auto-mergeable.

    See :doc:`../merging` for details.
    '''
    raise ConflictError('items cannot be merged')

  # other methods in SyncML spec:
  # def copyItem(self, item):                         raise NotImplementedError()
  # def execItem(self, item):                         raise NotImplementedError()
  # def moveItem(self, item):                         raise NotImplementedError()
  # def putItem(self, item):                          raise NotImplementedError()
  # def searchItem(self, item):                       raise NotImplementedError()

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
