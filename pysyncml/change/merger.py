# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/08/30
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
The ``pysyncml.change.merger`` is a helper package that provides
routines to help with managing change-specs on a slightly higher level
than `pysyncml.change.tracker` by actually detecting changes,
reporting them to a tracker and merging them back
together. Furthermore, it provides routines to help with the detection
and merging of text-based changes, either multi-line or singl-line
based.
'''

import urllib, hashlib, difflib
from .. import constants
from ..common import adict, state2string
from .tracker import *

#------------------------------------------------------------------------------
def uu(s):
  return urllib.unquote(s)

#------------------------------------------------------------------------------
def u(s):
  return urllib.quote(s)

#------------------------------------------------------------------------------
class Merger(object):
  '''
  Abstract base class for objects returned by the MergerFactory subclasses.
  '''
  def pushChangeSpec(self, changeSpec):
    raise NotImplementedError()
  def pushChange(self, attribute, currentValue, newValue):
    '''
    Record the change to the specified `attribute` from the original
    value `currentValue` to `newValue`. The merger object itself
    (i.e. ``self``) is returned, allowing multiple changes to be
    chained. The change-spec returned by :meth:`getChangeSpec` will be
    updated according to this merger's change detection strategy.

    If `currentValue` is ``None``, the field is assumed to be *added*.
    Conversely, if `newValue` is ``None``, the field is assumed to be
    *deleted*. If both are ``None`` (or, more generally speaking,
    equal), the request is ignored.
    '''
    raise NotImplementedError()
  def getChangeSpec(self):
    '''
    Returns the current change-spec representing all calls to
    :meth:`pushChange` since construction of this merger.
    '''
    raise NotImplementedError()
  def mergeChanges(self, attribute, localValue, remoteValue):
    '''
    Returns the value of the specified `attribute` as determined by
    the change-spec stored by this, the current `localValue` of this
    SyncML peer (i.e. the serve-side) and the client-provided
    `remoteValue` (i.e. of the remote client-side). Raises a
    `pysyncml.ConflictError` if the local changes conflict with the
    value provided by the remote peer.

    If `localValue` is ``None``, the field is assumed to not exist
    locally. Conversely, if `remoteValue` is ``None``, the field is
    assumed to not exist on the remote peer. If both are ``None`` (or,
    more generally speaking, equal), the value is returned as-is
    without further investigation.
    '''
    raise NotImplementedError()

#------------------------------------------------------------------------------
class MergerFactory(object):
  '''
  Abstract base class for factories to help with reporting and merging
  pysyncml change-specs.
  '''
  def newMerger(self, changeSpec=None):
    '''
    Returns a :class:`Merger` for the specified `changeSpec` which can
    be ``None`` if the merger is intended to generate a change-spec.
    '''
    raise NotImplementedError()

#------------------------------------------------------------------------------
class AttributeMergerFactory(MergerFactory):
  '''
  A merger factory for generating :class:`AttributeMerger` merger
  objects.
  '''
  def __init__(self, *args, **kw):
    super(AttributeMergerFactory, self).__init__(*args, **kw)
  def newMerger(self, changeSpec=None):
    return AttributeMerger(changeSpec)

#------------------------------------------------------------------------------
class AttributeMerger(Merger):
  '''
  A merger that simplifies usage of the
  :class:`pysyncml.AttributeChangeTracker
  <pysyncml.change.tracker.AttributeChangeTracker>` and allows it to
  be used by a CompositeMerger.
  '''

  #----------------------------------------------------------------------------
  def __init__(self, changeSpec, *args, **kw):
    super(AttributeMerger, self).__init__(*args, **kw)
    self.tracker = AttributeChangeTracker(changeSpec)

  #----------------------------------------------------------------------------
  def pushChangeSpec(self, changeSpec):
    self.tracker.pushChangeSpec(changeSpec)

  #----------------------------------------------------------------------------
  def pushChange(self, attribute, currentValue, newValue):
    if currentValue == newValue:
      return self
    if currentValue is None:
      self.tracker.append(attribute, constants.ITEM_ADDED)
    elif newValue is None:
      self.tracker.append(attribute, constants.ITEM_DELETED, currentValue)
    else:
      self.tracker.append(attribute, constants.ITEM_MODIFIED, currentValue)
    return self

  #----------------------------------------------------------------------------
  def getChangeSpec(self):
    return self.tracker.getChangeSpec()

  #----------------------------------------------------------------------------
  def mergeChanges(self, attribute, localValue, remoteValue):
    if localValue == remoteValue:
      return localValue
    # this will raise ConflictError if there is a conflict
    return self.tracker.update(attribute, localValue, remoteValue)

#------------------------------------------------------------------------------
class TextMergerFactory(MergerFactory):
  '''
  A merger factory for generating :class:`TextMerger` merger objects.
  '''
  def __init__(self, multiLine=True, *args, **kw):
    super(TextMergerFactory, self).__init__(*args, **kw)
    self.multiLine = multiLine
  def newMerger(self, changeSpec=None):
    return TextMerger(self.multiLine, changeSpec)

#------------------------------------------------------------------------------
class TextMerger(Merger):
  '''
  A merger that simplifies usage of the
  :class:`pysyncml.ListChangeTracker
  <pysyncml.change.tracker.ListChangeTracker>` and allows it to be
  used by a CompositeMerger.

  TODO: currently, the merging algorithm is fairly aggressive (i.e. it may
  merge changes that should probably be conflicts). This should be made an
  option to provide either aggressive or conservative merging.
  '''

  #----------------------------------------------------------------------------
  def __init__(self, multiLine, changeSpec, *args, **kw):
    super(TextMerger, self).__init__(*args, **kw)
    self.sep     = '\n' if multiLine else ' '
    self.tracker = ListChangeTracker(changeSpec)

  #----------------------------------------------------------------------------
  def pushChangeSpec(self, changeSpec):
    self.tracker.pushChangeSpec(changeSpec)

  #----------------------------------------------------------------------------
  def pushChange(self, currentText, newText):
    cur = currentText.split(self.sep)
    new = newText.split(self.sep)
    for index, offset, changeType, curValue, newValue in self._getChangeSets(cur, new):
      self.tracker.append(index + offset, changeType, curValue)
    return self

  #----------------------------------------------------------------------------
  def getChangeSpec(self):
    return self.tracker.getChangeSpec()

  #----------------------------------------------------------------------------
  def _getChangeSets(self, currentList, newList):
    sm = difflib.SequenceMatcher(a=currentList, b=newList)
    idxoffset = 0
    for opcode in sm.get_opcodes():
      if opcode[0] == 'equal':
        continue
      if opcode[0] == 'insert':
        for idx in range(opcode[3], opcode[4]):
          yield opcode[1], idxoffset, constants.ITEM_ADDED, None, newList[idx]
          idxoffset += 1
        continue
      if opcode[0] == 'replace':
        c0 = opcode[1]
        c1 = opcode[2]
        cD = c1 - c0
        c1 = c0 + min(cD, opcode[4] - opcode[3])
        for idx in range(c0, c1):
          yield idx, idxoffset, constants.ITEM_MODIFIED, \
            currentList[idx], newList[opcode[3] + idx - c0]
        # pseudo-inserts
        for idx in range(opcode[4] - opcode[3] - ( cD )):
          yield c1, idxoffset, constants.ITEM_ADDED, None, newList[opcode[3] + cD + idx]
          idxoffset += 1
        # pseudo-deletes
        for idx in range(c1, opcode[2]):
          yield idx, idxoffset, constants.ITEM_DELETED, currentList[idx], None
        continue
      if opcode[0] == 'delete':
        for idx in range(opcode[1], opcode[2]):
          yield idx, idxoffset, constants.ITEM_DELETED, currentList[idx], None
        continue
      raise Exception('unexpected difflib opcode "%s"' % (opcode[0],))

  #----------------------------------------------------------------------------
  def mergeChanges(self, localText, remoteText):
    if localText == remoteText:
      return localText
    cur  = localText.split(self.sep)
    new  = remoteText.split(self.sep)
    ret  = cur[:]
    tok  = None
    roff = 0
    for index, offset, changeType, curValue, newValue in self._getChangeSets(cur, new):
      change = self.tracker.isChange(index, changeType, newValue, token=tok)
      if change is None:
        continue
      change, tok = change
      if change is None:
        continue
      if changeType == constants.ITEM_DELETED:
        ret[change + roff] = None
      elif changeType == constants.ITEM_MODIFIED:
        ret[change + roff] = newValue
      elif changeType == constants.ITEM_ADDED:
        ret.insert(change + roff, newValue)
        roff += 1
      else:
        Exception('received unexpected change type %r' % (changeType,))
    return self.sep.join([e for e in ret if e is not None])

#------------------------------------------------------------------------------
class CompositeMergerFactory(MergerFactory):
  '''
  A merger factory for generating :class:`CompositeMerger` merger
  objects, which allows control of what kind of merger to use on a
  per-attribute basis.
  '''

  def __init__(self, sharedDefault=True, default=None, mergers=None, **kw):
    '''
    The CompositeMergerFactory constructor accepts the following
    parameters:

    :param default:

      The default merger factory (if unspecified, defaults to an
      AttributeMergerFactory). See `sharedDefault` if the default
      is not an attribute-based merger factory.

    :param mergers:

      A dictionary of (attribute => MergerFactory) that override the
      default merger factory for the specified attribute. If
      unspecified, all attributes will use the default merger factory.

    :param sharedDefault:

      The `sharedDefault` parameter controls how default attributes
      get handled. When ``True`` (the default), then all default
      attributes will share a Merger and the Merger will be passed the
      attribute name during operations. When ``False``, then each
      attribute will get its own Merger and operations will not get
      the attribute name. It is important that the `default` and
      `sharedDefault` parameters match - for example, if `default` is
      set to a ``TextMergerFactory``, then `sharedDefault` must be set
      to ``False``.
    '''
    self.shared  = sharedDefault
    self.default = default or AttributeMergerFactory()
    self.mergers = mergers or dict()
    self.mergers.update(kw)

  def newMerger(self, changeSpec=None):
    return CompositeMerger(self, changeSpec)

#------------------------------------------------------------------------------
class CompositeMerger(Merger):
  '''
  A composite merger is an attribute-based merger that allows a default
  merger for attributes to be specified, which can then be overridden for
  specific attributes.

    TODO: is there perhaps a better way to define when a subsidiary
    merger is a dispatch merger (i.e. takes the attribute name as
    operational parameter) than to use the factory "sharedDefault"
    parameter?
  '''

  #----------------------------------------------------------------------------
  def __init__(self, factory, changeSpec):
    self.factory = factory
    self.cspec   = changeSpec
    self.default = self.factory.default.newMerger()
    self.attrs   = dict()
    if changeSpec is not None:
      for cspec in changeSpec.split(';'):
        self.pushChangeSpec(cspec)

  #----------------------------------------------------------------------------
  def pushChangeSpec(self, changeSpec):
    for cspec in changeSpec.split('&'):
      if '=' not in cspec:
        self.default.pushChangeSpec(uu(cspec))
        continue
      attr, cspec = cspec.split('=', 1)
      self._getMerger(uu(attr)).pushChangeSpec(uu(cspec))
    return self

  #----------------------------------------------------------------------------
  def _getMerger(self, attribute):
    if attribute in self.attrs:
      return self.attrs[attribute]
    if attribute in self.factory.mergers:
      self.attrs[attribute] = self.factory.mergers[attribute].newMerger()
      return self.attrs[attribute]
    if not self.factory.shared:
      self.attrs[attribute] = self.factory.default.newMerger()
      return self.attrs[attribute]
    return self.default

  #----------------------------------------------------------------------------
  def pushChange(self, attribute, currentValue, newValue):
    merger = self._getMerger(attribute)
    if merger is self.default:
      merger.pushChange(attribute, currentValue, newValue)
    else:
      merger.pushChange(currentValue, newValue)
    return self

  #----------------------------------------------------------------------------
  def getChangeSpec(self):
    ret = self.cspec or ''
    if len(ret) > 0:
      ret += ';'
    if self.default.getChangeSpec() is None:
      return None
    ret += u(self.default.getChangeSpec())
    for attr in sorted(self.attrs.iterkeys()):
      cspec = self.attrs[attr].getChangeSpec()
      if cspec is None:
        return None
      if len(cspec) <= 0:
        continue
      if len(ret) > 0 and ret[-1] != ';':
        ret += '&'
      ret += u(attr) + '=' + u(cspec)
    return ret

  #----------------------------------------------------------------------------
  def mergeChanges(self, attribute, localValue, remoteValue):
    merger = self._getMerger(attribute)
    if merger is self.default:
      return merger.mergeChanges(attribute, localValue, remoteValue)
    return merger.mergeChanges(localValue, remoteValue)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
