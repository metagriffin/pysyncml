# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/08/29
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
The ``pysyncml.change.tracker`` is a helper package that provides
routines to generate and parse change-specs that are compliant with
pysyncml's change tracking system.
'''

import urllib, hashlib
from .. import constants
from ..common import adict, state2string, ConflictError

#------------------------------------------------------------------------------
class InvalidChangeSpec(Exception): pass

#------------------------------------------------------------------------------
def uu(s):
  return urllib.unquote(s)

#------------------------------------------------------------------------------
def u(s):
  return urllib.quote(s)

#------------------------------------------------------------------------------
def isMd5Equal(val1, md51, val2, md52):
  if md51 or md52:
    val1 = val1 if md51 else hashlib.md5(val1).hexdigest()
    val2 = val2 if md52 else hashlib.md5(val2).hexdigest()
    return val1 == val2
  return val1 == val2

#------------------------------------------------------------------------------
class ChangeTracker(object):
  '''
  A ChangeTracker is an abstract interface to help with generating, parsing,
  and managing pysyncml change-specs. See :doc:`../merging` for details on
  change-spec handling.
  '''

  #----------------------------------------------------------------------------
  def __init__(self, changeSpec=None, *args, **kw):
    super(ChangeTracker, self).__init__(*args, **kw)
    self.pushChangeSpec(changeSpec)

  #----------------------------------------------------------------------------
  def pushChangeSpec(self, changeSpec=None):
    if changeSpec is None:
      return
    if ';' in changeSpec:
      for spec in changeSpec.split(';'):
        self.pushChangeSpec(spec)
      return
    self._pushChangeSpec(changeSpec)

  #----------------------------------------------------------------------------
  def _pushChangeSpec(self, changeSpec):
    for opspec in changeSpec.split('|'):
      op, flist = opspec.split(':', 1)
      if op not in ('add', 'mod', 'del'):
        raise InvalidChangeSpec(opspec)
      op = {'add': constants.ITEM_ADDED,
            'mod': constants.ITEM_MODIFIED,
            'del': constants.ITEM_DELETED,
            }[op]
      for fspec in flist.split(','):
        if op == constants.ITEM_ADDED:
          self.append(uu(fspec), op)
        else:
          fname, init = fspec.split('@', 1)
          if init[0] == 'm':
            if len(init) != 33:
              raise InvalidChangeSpec('bad initial value md5 in field spec: %r' % (fspec,))
            ismd5 = True
            init  = init[1:]
          elif init[0] == 'v':
            ismd5 = False
            init  = uu(init[1:])
          else:
            raise InvalidChangeSpec('bad initial value encoding in field spec: %r' % (fspec,))
          self.append(uu(fname), op, initialValue=init, isMd5=ismd5)

  #----------------------------------------------------------------------------
  def append(self, fieldname, changeType, initialValue=None, isMd5=False):
    '''
    Add a change to this ChangeTracker.

    :param fieldname:

      The item attribute that was changed in some way. The type of
      `fieldname` is dependent on which subclass of ChangeTracker is
      being used.

    :param changeType:

      The type of change that was applied to `fieldname`, which can be
      one of ``pysyncml.ITEM_ADDED``, ``pysyncml.ITEM_MODIFIED``, or
      ``pysyncml.ITEM_DELETED``.

    :param initialValue:

      For non-ADDED change types, specifies the *initial* value of the
      field, before the change was applied. Note that if the
      `initialValue` is very large, an MD5 checksum can be provided
      instead, in which case `isMd5` should be set to ``True``.

    :param isMd5:

      Specifies whether `initialValue` is an MD5 checksum or not. For
      large values of `initialValue` the ChangeTrackers will
      automatically convert it to a checksum, but this allows the
      caller to potentially do some additional optimizations.
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  def isChange(self, fieldname, changeType, newValue=None, isMd5=False):
    '''
    Checks to see if the specified field should be changed to the
    `newValue`, first checking to see if the change conflicts with the
    change-spec stored by this ChangeTracker. IMPORTANT: the
    `changeType` is relative to the **current** local value, as
    recorded by the changes stored by this tracker from the
    **initial** value.

    See :meth:`update` for a layer above.

    This method will terminate in one of the following three ways:

    * returns None:

      The `newValue` is actually outdated, but does not conflict.
      The field should be left as-is.

    * returns `changeObject`:

      If any form of change should be applied as a result of this
      change request, then `changeObject` will be non-None and will
      define how. The exact nature of the object is ChangeTracker
      subclass dependent.

    * raises `pysyncml.ConflictError`:

      The `newValue` conflicts with a change made by another source
      and should be handled by following conflict resolution policy.

    For example, if two clients and a server are tracking changes
    made to the following fields::

      initial values (on server, client 1 and client 2):
        field "a" => "A"    (will not change)
        field "b" => "B"    (will be modified by client 1)
        field "c" => "C"    (will be deleted by client 1)
        field "d" => "D"    (will be modified by client 2)
        field "e" => "E"    (will be a conflict)
        field "f" => "F"    (will be modified identically)

      client 1 changes:
        does not alter field "a"
        modifies field "b" to "Bmod"
        deletes field "c"
        does not alter field "d"
        deletes field "e"
        modifies field "f" to "Fmod"

      client 2 changes (simultaneous to client 1 changes):
        does not alter field "a"
        does not alter field "b"
        does not alter field "c"
        modifies field "d" to "Dmod"
        modifies field "e" to "Emod"
        modifies field "f" to "Fmod"

      client 1 synchronizes with server ==> server values:
        field "b" => "Bmod"
        deletes fields "c" and "e"
        field "f" => "Fmod"
        change-spec for client 2: "mod:b@vB,f@vF|del:c@vC,e@vE"

      when client 2 synchronizes, the framework detects a conflict and
      requests a merge attempt by the agent. the agent then compares the
      current values and those presented by client 2 and determines:
        - field "a" is unchanged
        - field "b" differs: changed to "B"
        - field "c" differs: added as "C"
        - field "d" differs: change to "Dmod"
        - field "e" differs: added as "Dmod"
        - field "f" is unchanged

      for the fields that are mismatches (i.e. fields "b", "c", "d",
      and "e"), the agent checks with this change tracker ("ct") to
      see if it was actually a change, and if so, if it conflicts:

        - ct.isChange('b', 'B')    ==> None
        - ct.isChange('c', 'C')    ==> None
        - ct.isChange('d', 'Dmod') ==> 'd'
        - ct.isChange('e', 'Emod') ==> raises ConflictError

    Note that this assumes that the caller will have verified that the
    remote `currentValue` is **not** equal to the local active value -
    i.e. that there is some difference between the `fieldname` values,
    and a resolution needs to be negotiated.

    :param newValue:

      A string representing the value that is being tested for
      conflicts or outdated-ness.

    .. TODO:: perhaps rename this method?...
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  def update(self, fieldname, localValue, remoteValue):
    '''
    Returns the appropriate current value, based on the changes
    recorded by this ChangeTracker, the value stored by the server
    (`localValue`), and the value stored by the synchronizing client
    (`remoteValue`). If `remoteValue` conflicts with changes stored
    locally, then a `pysyncml.ConflictError` is raised.

    If a change needs to be applied because `remoteValue` has been
    updated, then the new value will be returned, and this
    ChangeTracker will be updated such that a call to
    :meth:`getChangeSpec` will incorporate the change.

    :param fieldname:

      The name of the fieldname being evaluated.

    :param localValue:

      The value of the field as stored by the server, usually the one that
      also stored the current change-spec. If `localValue` is ``None``,
      then it is assumed that the field was potentially added (this will
      first be verified against the stored change-spec).

    :param remoteValue:

      The new value being presented that may or may not be a source of
      conflict. If `remoteValue` is ``None``, then it is assumed that
      the field was potentially deleted (this will first be verified
      against the stored change-spec).

    '''
    if localValue == remoteValue:
      return localValue
    ct = constants.ITEM_DELETED if remoteValue is None else constants.ITEM_MODIFIED
    if localValue is None:
      ct = constants.ITEM_ADDED

    # todo: i should probably trap irep errors. for example, if this
    #       cspec has a field "x" marked as deleted, then `localValue`
    #       must be None... etc.

    # TODO: i think this kind of handling would break in ListChangeTracker!...

    changed = self.isChange(fieldname, ct, remoteValue)
    if changed is None:
      return localValue
    self.append(changed, ct, initialValue=localValue, isMd5=False)
    return remoteValue

  #----------------------------------------------------------------------------
  def getFullChangeSpec(self):
    '''
    Returns a string-representation of *all* changes recorded by this
    ChangeTracker, including those provided in the constructor and any
    calls to `pushChangeSpec()`. Note that this is usually *NOT* what
    you are looking for when reporting changes to the pysyncml
    framework -- for that, see :meth:`getChangeSpec`.
    '''
    return self._changes2spec(self.allchanges)

  #----------------------------------------------------------------------------
  def getChangeSpec(self):
    '''
    Returns a string-representation of the changes recorded by this
    ChangeTracker that were reported since construction (or calls to
    pushChangeSpec()) by calls to :meth:`append` or :meth:`update`.

    This is similar to, but distinct from, :meth:`getFullChangeSpec`.
    '''
    return self._changes2spec(self.changes)

  #----------------------------------------------------------------------------
  def _changes2spec(self, changes):
    clist = dict(((constants.ITEM_ADDED, []),
                  (constants.ITEM_MODIFIED, []),
                  (constants.ITEM_DELETED, [])))
    for optype, field, spec in changes:
      clist[optype].append((field, spec))
    ret = ''
    if len(clist[constants.ITEM_ADDED]) > 0:
      ret += 'add:' + ','.join([e[0] for e in clist[constants.ITEM_ADDED]])
    if len(clist[constants.ITEM_MODIFIED]) > 0:
      if len(ret) > 0:
        ret += '|'
      ret += 'mod:' + ','.join([e[0] + e[1] for e in clist[constants.ITEM_MODIFIED]])
    if len(clist[constants.ITEM_DELETED]) > 0:
      if len(ret) > 0:
        ret += '|'
      ret += 'del:' + ','.join([e[0] + e[1] for e in clist[constants.ITEM_DELETED]])
    return ret

  #----------------------------------------------------------------------------
  def __str__(self):
    return self.getFullChangeSpec()

#------------------------------------------------------------------------------
class AttributeChangeTracker(ChangeTracker):
  '''
  A ChangeTracker implementation that manages changes made to attributes
  that are completely independent of each other.
  '''

  #----------------------------------------------------------------------------
  def __init__(self, changeSpec=None, *args, **kw):
    '''
    Initializes this AttributeChangeTracker with the provided
    `changeSpec`, which is expected to be in the same format as what
    would have been returned by a call to ``str()`` on this
    object. The change-spec will look similar to::

      add:tel-home|mod:firstname@m68b329d...,lastname@mh4d9...|del:tel-pager@mba45...

    If `changeSpec` is not specified, this AttributeChangeTracker will
    start assuming no prior changes were made to any fields.
    '''
    self.baseline = dict()
    self.current  = dict()
    super(AttributeChangeTracker, self).__init__(changeSpec, *args, **kw)

  #----------------------------------------------------------------------------
  @property
  def allchanges(self):
    changes = self._collapseChanges(self.baseline, self.current)
    for key in sorted(changes.keys()):
      val = changes[key]
      if val.op == constants.ITEM_ADDED:
        yield (val.op, u(key), None)
      else:
        yield (val.op, u(key), '@' + ( 'm' if val.md5 else 'v' ) + u(val.ival))

  #----------------------------------------------------------------------------
  @property
  def changes(self):
    changes = self.current
    for key in sorted(changes.keys()):
      val = changes[key]
      if val.op == constants.ITEM_ADDED:
        yield (val.op, u(key), None)
      else:
        yield (val.op, u(key), '@' + ( 'm' if val.md5 else 'v' ) + u(val.ival))

  #----------------------------------------------------------------------------
  def pushChangeSpec(self, changeSpec=None):
    if len(self.current) > 0:
      self.baseline = self._collapseChanges(self.baseline, self.current)
      self.current  = dict()
    super(AttributeChangeTracker, self).pushChangeSpec(changeSpec)
    if len(self.current) > 0:
      self.baseline = self._collapseChanges(self.baseline, self.current)
      self.current  = dict()

  #----------------------------------------------------------------------------
  def _collapseChanges(self, baseline, current):
    if len(baseline) <= 0:
      return current
    if len(current) <= 0:
      return baseline
    ret = baseline.copy()
    for key, val in current.items():
      if key not in ret:
        ret[key] = val
        continue
      nval = ret[key].copy()
      ret[key] = nval
      if val.op != constants.ITEM_DELETED:
        continue
      if nval.op == constants.ITEM_ADDED:
        del ret[key]
        continue
      nval.op = constants.ITEM_DELETED
    return ret

  #----------------------------------------------------------------------------
  def append(self, fieldname, changeType, initialValue=None, isMd5=False):

    # todo: if a field is changed: "a" => "b" => "a", then the change-spec
    #       should not include any changes to that field. unfortunately, i
    #       do not have access to what the field was changed *to*, so
    #       therefore cannot implement that. :(

    if not isMd5 and initialValue is not None and len(initialValue) > 32:
      initialValue = hashlib.md5(initialValue).hexdigest()
      isMd5        = True
    if fieldname not in self.current:
      self.current[fieldname] = adict(op   = changeType,
                                      ival = initialValue,
                                      md5  = isMd5)
      return
    cur = self.current[fieldname]
    if cur.op == changeType:
      return
    if changeType == constants.ITEM_DELETED:
      if cur.op == constants.ITEM_ADDED:
        del self.current[fieldname]
        return
      cur.op = constants.ITEM_DELETED

  #----------------------------------------------------------------------------
  def isChange(self, fieldname, changeType, newValue=None, isMd5=False):
    '''
    Implements as specified in :meth:`.ChangeTracker.isChange` where
    the `changeObject` is simply the fieldname that needs to be
    updated with the `newValue`. Currently, this is always equal to
    `fieldname`.
    '''
    # todo: this seems inefficient...
    changes = self._collapseChanges(self.baseline, self.current)
    if fieldname not in changes:
      return fieldname
    cur = changes[fieldname]
    if changeType == constants.ITEM_DELETED:
      if cur.op == constants.ITEM_ADDED or cur.op == constants.ITEM_DELETED:
        # the field is deleted because it hasn't been added yet
        # (the check for cur.op == constants.ITEM_DELETED should
        # never be true, so just here for paranoia...)
        return None
      # we are requiring that the current/new values are different,
      # thus there is a collision between the added values
      raise ConflictError('conflicting deletion of field "%s"'
                                 % (fieldname,))

    # the `newValue` is different than the current value (otherwise
    # this method should not have been called) -- either it was added
    # or modified.

    # if it appears to be "added", then it may be because it was
    # deleted in this tracker.

    # if it appears to be "modified", then it may be because it
    # was modified in this tracker.

    # in either case, check to see if it is equal to the initial
    # value, and if it was, then there was actually no change.

    if isMd5Equal(newValue, isMd5, cur.ival, cur.md5):
      # the new value is equal to the initial value, so this
      # field was not changed (but has local changes)
      return None

    # the new value is not equal to the initial value, which means
    # that they were both changed and/or added.
    raise ConflictError(
      'conflicting addition or modification of field "%s"' % (fieldname,))

#------------------------------------------------------------------------------
class ListChangeTracker(ChangeTracker):
  '''
  A ChangeTracker implementation that manages changes made to an
  ordered sequence of elements. This tracker is aware that (and
  adjusts for the fact that) the addition or deletion of an element in
  the list can impact the indexing of elements that come sequentially
  after the change. The most common use of the ListChangeTracker is to
  track changes to text that has been broken down into sequences of
  lines or words.
  '''

  #----------------------------------------------------------------------------
  def __init__(self, changeSpec=None, *args, **kw):
    '''
    Initializes this ListChangeTracker with the provided `changeSpec`,
    which is expected to be in the same format as what would have been
    returned by a call to ``str()`` on this object. The change-spec
    will look similar to::

      2:a,1:M68b329d...,1:mh4d9,2:Dba45...,3:a

    If `changeSpec` is not specified, this ListChangeTracker will
    start assuming no prior changes were made to any content and will
    expect changes to be reported via :meth:`pushChange`.
    '''
    self.baseline = []
    self.current  = []
    super(ListChangeTracker, self).__init__(changeSpec, *args, **kw)

  #----------------------------------------------------------------------------
  @property
  def allchanges(self):
    return self._changes2struct(self._collapseChanges(self.baseline, self.current))

  #----------------------------------------------------------------------------
  @property
  def changes(self):
    return self._changes2struct(self.current)

  #----------------------------------------------------------------------------
  def _changes2struct(self, changes):
    for val in changes:
      op = {
        constants.ITEM_ADDED:    'a',
        constants.ITEM_MODIFIED: 'M' if val.md5 else 'm',
        constants.ITEM_DELETED:  'D' if val.md5 else 'd',
        }[val.op]
      if val.op == constants.ITEM_ADDED:
        yield (val.op, val.index, op)
      else:
        yield (val.op, val.index, op + u(val.ival))

  #----------------------------------------------------------------------------
  def _changes2spec(self, changes):
    last = 0
    ret = ''
    for optype, index, fspec in changes:
      if len(ret) > 0:
        ret += ','
      ret += str(index - last) + ':' + fspec
      last = index
    return ret

  #----------------------------------------------------------------------------
  def pushChangeSpec(self, changeSpec=None):
    if len(self.current) > 0:
      self.baseline = self._collapseChanges(self.baseline, self.current)
      self.current  = []
    super(ListChangeTracker, self).pushChangeSpec(changeSpec)
    if len(self.current) > 0:
      self.baseline = self._collapseChanges(self.baseline, self.current)
      self.current  = []

  #----------------------------------------------------------------------------
  def _pushChangeSpec(self, changeSpec):
    last = 0
    for opspec in changeSpec.split(','):
      index, spec = opspec.split(':', 1)
      index = int(index) + last
      op, md5 = {'a': (constants.ITEM_ADDED, True),
                 'm': (constants.ITEM_MODIFIED, False),
                 'M': (constants.ITEM_MODIFIED, True),
                 'd': (constants.ITEM_DELETED, False),
                 'D': (constants.ITEM_DELETED, True),
                 }[spec[0]]
      if op == constants.ITEM_ADDED:
        self.append(index, op)
      else:
        self.append(index, op, uu(spec[1:]), md5)
      last = index

  #----------------------------------------------------------------------------
  def append(self, listIndex, changeType, initialValue=None, isMd5=False):
    '''
    Adds a change spec to the current list of changes. The `listIndex`
    represents the line number (in multi-line mode) or word number (in
    single-line mode), and must be **INCLUSIVE** of both additions and
    deletions.
    '''
    if not isMd5 and initialValue is not None and len(initialValue) > 32:
      initialValue = hashlib.md5(initialValue).hexdigest()
      isMd5        = True
    cur = adict(index = int(listIndex),
                op    = changeType,
                ival  = initialValue,
                md5   = isMd5)
    for idx, val in enumerate(self.current):
      if val.index < cur.index:
        continue
      if val.index > cur.index:
        self.current.insert(idx, cur)
        break
      # todo: this should never happen... (there should not be a change
      #       reported for the same line without a `pushChangeSpec()` between)
      # todo: perhaps attempt a merging?...
      raise InvalidChangeSpec('conflicting changes for index %d' % (cur.index,))
    else:
      self.current.append(cur)

  #----------------------------------------------------------------------------
  def isChange(self, listIndex, changeType, newValue=None, isMd5=False, token=None):
    '''
    Implements as specified in :meth:`.ChangeTracker.isChange` where
    the `changeObject` is a two-element tuple. The first element is
    the index at which the change should be applied, and the second
    element is an abstract token that should be passed back into this
    method at every iteration.

    IMPORTANT: unlike the AttributeChangeTracker, the
    ListChangeTracker's `isChange()` method is sensitive to order
    (which is why it uses the `changeObject` and `token`
    mechanisms. Therefore, it is important to call `isChange()`
    sequentially with all changes in the order that they occur in the
    change list.
    '''

    # THE INDEX PASSED TO ListChangeTracker.isChange() DOES NOT INCLUDE:
    #   - local deletions
    #   - remote additions

    adjust  = 0               # tracks local deletes
    token   = token           # tracks consecutive addition adjustments
    index   = int(listIndex)
    ret     = index

    # todo: this should reduce complexity later on, but something
    #       went wrong...
    # if changeType != constants.ITEM_ADDED:
    #   token = None
    # else:
    #   if token is None or token[0] != index:
    #     token = (ret, 0)
    #   token = (ret, token[1] + 1)

    # todo: this seems inefficient...
    changes = self._collapseChanges(self.baseline, self.current)

    for cur in changes:
      if cur.index > index:
        if changeType != constants.ITEM_ADDED:
          return (ret, None)
        if token is None or token[0] != index - adjust:
          token = (ret, 0)
        token = (ret, token[1] + 1)
        return (ret, token)

      if cur.index != index:
        if cur.op == constants.ITEM_DELETED:
          index  += 1
          adjust += 1
        continue

      if token is not None and token[0] == index - adjust:
        index += token[1]
        continue

      if changeType == constants.ITEM_DELETED:
        if cur.op == constants.ITEM_ADDED:
          # the field is deleted because it hasn't been added yet
          return (None, None)
        # we are requiring that the current/new values are different,
        # thus there is a collision between the added values
        raise ConflictError(
          'conflicting deletion of list index %r' % (index,))

      if changeType == constants.ITEM_ADDED:
        if token is None:
          token = (ret, 0)
        token = (ret, token[1] + 1)
        if cur.op == constants.ITEM_DELETED:
          if isMd5Equal(newValue, isMd5, cur.ival, cur.md5):
            return (None, token)
          # todo: this *could* be a del-mod *conflict*... but not
          #       *NECESSARILY* so, since it could be a
          #       del-adjacent-add, which is not a problem. in the
          #       conflict case, the resolution will cause the
          #       modified line to silently win.
          # TODO: perhaps i should err on the side of safety and
          #       issue a ConflictError?...
        return (ret, token)

      if cur.op == constants.ITEM_DELETED:
        index  += 1
        adjust += 1
        continue

      # changeType = mod, op = add/mod

      if cur.op == constants.ITEM_ADDED:
        # todo: i'm not sure if this case is even possible...
        raise ConflictError(
          'conflicting addition of list index %r' % (index,))

      # mod/mod - check initvalue

      if isMd5Equal(newValue, isMd5, cur.ival, cur.md5):
        # the new value is equal to the initial value, so this
        # line was not changed (but has local changes)
        return (None, None)
      # the new value is not equal to the initial value, which means
      # that they were both changed and/or added.
      raise ConflictError(
        'conflicting modification of list index %r' % (index,))

    if changeType != constants.ITEM_ADDED:
      return (ret, None)
    if token is None or token[0] != index - adjust:
      token = (ret, 0)
    token = (ret, token[1] + 1)
    return (ret, token)

  #----------------------------------------------------------------------------
  def _collapseChanges(self, baseline, current):

    # TODO: collapseChanges gets called many times... perhaps it
    #       would make sense to cache it...

    baseline = [e.copy() for e in baseline]
    current  = [e.copy() for e in current]
    baseline.sort(key=lambda e: e.index)
    current.sort(key=lambda e: e.index)

    if len(current) == 0:
      return baseline

    if len(baseline) == 0:
      return current

    # first pass: adjust all indices so that they refer to the same
    # values by adjusting for DELETEs in baseline and ADDs in current

    bidx = 0
    cidx = 0

    while bidx < len(baseline) and cidx < len(current):
      curinc = False
      basinc = False
      if baseline[bidx].index < current[cidx].index:
        if baseline[bidx].op != constants.ITEM_DELETED:
          bidx += 1
          continue
        curinc = True
      elif baseline[bidx].index > current[cidx].index:
        if current[cidx].op != constants.ITEM_ADDED:
          cidx += 1
          continue
        basinc = True
      else:
        if baseline[bidx].op != constants.ITEM_DELETED \
           and current[cidx].op != constants.ITEM_ADDED:
          bidx += 1
          cidx += 1
          continue
        curinc = True
        basinc = True
      if curinc:
        for idx in range(cidx, len(current)):
          if current[idx].index >= baseline[bidx].index:
            current[idx].index += 1
        bidx += 1
      if basinc:
        for idx in range(bidx, len(baseline)):
          if baseline[idx].index >= current[cidx].index:
            baseline[idx].index += 1
        cidx += 1

    # second pass: merge changes, negotiating changes to the same
    # line, and removing changes that cancel each other out.

    hasNone = False
    for change in current:

      handled = False

      insert = None
      for idx, bchange in enumerate(baseline):
        if bchange.index > change.index:
          insert = idx
          break
        if bchange.index == change.index:
          if change.op == constants.ITEM_ADDED:
            raise Exception('internal error: ADDED state on existing index %d'
                            % (bchange.index,))
          elif change.op == constants.ITEM_MODIFIED:
            if bchange.op in (constants.ITEM_ADDED, constants.ITEM_MODIFIED):
              handled = True
              break
            raise Exception('unexpected MODIFIED state on DELETED index on %d'
                            % (bchange.index,))
          elif change.op == constants.ITEM_DELETED:
            if bchange.op == constants.ITEM_ADDED:
              bchange.op = None
              hasNone = True
            else:
              bchange.op = constants.ITEM_DELETED
            handled = True
            break
          else:
            raise Exception('unexpected change type %r' % (change.op,))

      if handled:
        continue

      if insert is None:
        baseline.append(change)
      else:
        baseline.insert(insert, change)

    if not hasNone:
      return baseline

    remcnt = 0
    for change in baseline:
      if change.op is None:
        remcnt += 1
        continue
      change.index -= remcnt

    return [e for e in baseline if e.op is not None]

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
