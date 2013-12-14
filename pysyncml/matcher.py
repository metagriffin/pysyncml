# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/05/30
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
The ``pysyncml.matcher`` provides automated DataStore selection.
'''

from . import constants
import difflib
from itertools import product

#------------------------------------------------------------------------------
def has_ct(a, b, checkVersion, transmit, wildcard):
  a = [e for e in a if ( e.transmit if transmit else e.receive )]
  b = [e for e in b if ( e.transmit if transmit else e.receive )]
  for ct_a in a:
    for ct_b in b:
      if ct_a.ctype == ct_b.ctype:
        if not checkVersion:
          return True
        for v_a in ct_a.versions:
          if v_a in ct_b.versions:
            return True
  return False

#------------------------------------------------------------------------------
def has_ct_both(a, b, checkVersion, wildcard):
  return has_ct(a, b, checkVersion, True, wildcard) \
         and has_ct(a, b, checkVersion, False, wildcard)

#------------------------------------------------------------------------------
def cmpToDataStore_ct_set(base, ds1, ds2):
  if has_ct_both(base, ds1, True, False):    return -1
  if has_ct_both(base, ds2, True, False):    return 1
  if has_ct_both(base, ds1, False, False):   return -1
  if has_ct_both(base, ds2, False, False):   return 1
  if has_ct_both(base, ds1, True, True):     return -1
  if has_ct_both(base, ds2, True, True):     return 1
  if has_ct_both(base, ds1, False, True):    return -1
  if has_ct_both(base, ds2, False, True):    return 1
  return 0

#------------------------------------------------------------------------------
def cmpToDataStore_ct_pref(base, ds1, ds2):
  basect = [ct for ct in base.contentTypes if ct.preferred]
  ds1ct  = [ct for ct in ds1.contentTypes if ct.preferred]
  ds2ct  = [ct for ct in ds2.contentTypes if ct.preferred]
  return cmpToDataStore_ct_set(basect, ds1ct, ds2ct)

#------------------------------------------------------------------------------
def cmpToDataStore_ct_all(base, ds1, ds2):
  return cmpToDataStore_ct_set(base.contentTypes, ds1.contentTypes,
                               ds2.contentTypes)

#------------------------------------------------------------------------------
def cmpToDataStore_ct(base, ds1, ds2):
  ret = cmpToDataStore_ct_pref(base, ds1, ds2)
  if ret != 0:
    return ret
  return cmpToDataStore_ct_all(base, ds1, ds2)

#------------------------------------------------------------------------------
def cmpToDataStore_uri(base, ds1, ds2):
  '''Bases the comparison of the datastores on URI alone.'''
  ret = difflib.get_close_matches(base.uri, [ds1.uri, ds2.uri], 1, cutoff=0.5)
  if len(ret) <= 0:
    return 0
  if ret[0] == ds1.uri:
    return -1
  return 1

#------------------------------------------------------------------------------
def cmpToDataStore(base, ds1, ds2):
  ret = cmpToDataStore_ct(base, ds1, ds2)
  if ret != 0:
    return ret
  return cmpToDataStore_uri(base, ds1, ds2)

#------------------------------------------------------------------------------
def _chkpref(source, target, prefcnt):
  if prefcnt <= 0:
    return True
  if prefcnt == 1:
    return source.preferred or target.preferred
  return source.preferred and target.preferred

#------------------------------------------------------------------------------
def _pickTransmitContentType(source, target, prefcnt, checkVersion):
  for sct in source:
    for tct in target:
      if sct.ctype != tct.ctype:
        continue
      if not checkVersion:
        if _chkpref(sct, tct, prefcnt):
          return (sct.ctype, reversed(sct.versions)[0])
        continue
      for sv in reversed(sct.versions):
        for tv in reversed(tct.versions):
          if sv != tv:
            continue
          if _chkpref(sct, tct, prefcnt):
            return (sct.ctype, sv)
  return None

#------------------------------------------------------------------------------
def pickTransmitContentType(source, target):

  # TODO: this is probably not the most efficient algorithm!...
  #       (but it works... ;-)

  # order of preference:
  #   - transmit => receive, BOTH preferred, VERSION match
  #   - transmit => receive, ONE preferred, VERSION match
  #   - transmit => receive, neither preferred, VERSION match
  #   - transmit => receive, BOTH preferred, no version match
  #   - transmit => receive, ONE preferred, no version match
  #   - transmit => receive, neither preferred, no version match
  #   - tx/rx => tx/rx, BOTH preferred, VERSION match
  #   - tx/rx => tx/rx, ONE preferred, VERSION match
  #   - tx/rx => tx/rx, neither preferred, VERSION match
  #   - tx/rx => tx/rx, BOTH preferred, no version match
  #   - tx/rx => tx/rx, ONE preferred, no version match
  #   - tx/rx => tx/rx, neither preferred, no version match

  # todo: make it explicit (or overrideable) that i am depending on the ordering
  #       of the versions supported to give an indicator of preference...

  sct = source.contentTypes
  tct = target.contentTypes

  def fct(set, transmit):
    if transmit:
      return [ct for ct in set if ct.transmit]
    return [ct for ct in set if ct.receive]

  return \
    _pickTransmitContentType(fct(sct, True), fct(tct, False), 2, True) \
    or _pickTransmitContentType(fct(sct, True), fct(tct, False), 1, True) \
    or _pickTransmitContentType(fct(sct, True), fct(tct, False), 0, True) \
    or _pickTransmitContentType(fct(sct, True), fct(tct, False), 2, False) \
    or _pickTransmitContentType(fct(sct, True), fct(tct, False), 1, False) \
    or _pickTransmitContentType(fct(sct, True), fct(tct, False), 0, False) \
    or _pickTransmitContentType(sct, tct, 2, True) \
    or _pickTransmitContentType(sct, tct, 1, True) \
    or _pickTransmitContentType(sct, tct, 0, True) \
    or _pickTransmitContentType(sct, tct, 2, False) \
    or _pickTransmitContentType(sct, tct, 1, False) \
    or _pickTransmitContentType(sct, tct, 0, False) \
    or None

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
