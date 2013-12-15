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

import unittest, re

from .. import common, constants
from ..common import adict, ConflictError
from .tracker import AttributeChangeTracker, ListChangeTracker

#------------------------------------------------------------------------------
class TestAttributeChangeTracker(unittest.TestCase):

  maxDiff = None

  #----------------------------------------------------------------------------
  def test_null(self):
    ct = AttributeChangeTracker()
    self.assertEqual(ct.getFullChangeSpec(), '')
    self.assertEqual(ct.getChangeSpec(), '')
    ct = AttributeChangeTracker('add:first|mod:mi@vJ|del:tel-pager@v1234')
    self.assertEqual(ct.getFullChangeSpec(), 'add:first|mod:mi@vJ|del:tel-pager@v1234')
    self.assertEqual(ct.getChangeSpec(), '')
    ct = AttributeChangeTracker('add:first|mod:mi@vJ|del:tel-pager@v1234')
    ct.append('last', constants.ITEM_ADDED)
    self.assertEqual(ct.getFullChangeSpec(), 'add:first,last|mod:mi@vJ|del:tel-pager@v1234')
    self.assertEqual(ct.getChangeSpec(), 'add:last')

  #----------------------------------------------------------------------------
  def test_changespec_gen_simple(self):
    ct = AttributeChangeTracker()
    ct.append('first', constants.ITEM_ADDED)
    ct.append('tel-pager', constants.ITEM_DELETED, '1234')
    ct.append('surname', constants.ITEM_MODIFIED, 'Smith')
    ct.append('mi', constants.ITEM_MODIFIED, 'J')
    chk = 'add:first|mod:mi@vJ,surname@vSmith|del:tel-pager@v1234'
    self.assertEqual(str(ct), chk)

  #----------------------------------------------------------------------------
  def test_changespec_gen_simpleWithEscape(self):
    ct = AttributeChangeTracker()
    ct.append('first', constants.ITEM_ADDED)
    ct.append('tel-pager', constants.ITEM_DELETED, '+1-888-555-1212')
    ct.append('surname', constants.ITEM_MODIFIED, 'Smith')
    ct.append('mi', constants.ITEM_MODIFIED, 'J')
    chk = 'add:first|mod:mi@vJ,surname@vSmith|del:tel-pager@v%2B1-888-555-1212'
    self.assertEqual(str(ct), chk)

  #----------------------------------------------------------------------------
  def test_changespec_gen_overwrite(self):
    ct = AttributeChangeTracker()
    ct.append('mi', constants.ITEM_MODIFIED, 'J')
    ct.append('first', constants.ITEM_ADDED)
    ct.append('tel-pager', constants.ITEM_DELETED, '1234')
    ct.append('surname', constants.ITEM_MODIFIED, 'Smith')
    ct.append('mi', constants.ITEM_DELETED, 'K')
    chk = 'add:first|mod:surname@vSmith|del:mi@vJ,tel-pager@v1234'
    self.assertEqual(str(ct), chk)

  #----------------------------------------------------------------------------
  def test_changespec_parse_overwrite(self):
    ct = AttributeChangeTracker('add:first|mod:mi@vJ,surname@vSmith|del:tel-pager@v1234')
    ct.append('mi', constants.ITEM_DELETED, 'K')
    chk = 'add:first|mod:surname@vSmith|del:mi@vJ,tel-pager@v1234'
    self.assertEqual(str(ct), chk)

  #----------------------------------------------------------------------------
  def test_conflict(self):
    ct = AttributeChangeTracker(
      'add:first|mod:mi@vJ,surname@vSmith|del:tel-pager@v1234')
    # note: not checking for identical changes at the ChangeTracker level
    #       since that should be done at the agent level (ie. if new remote
    #       value == new local value --> no problem).
    with self.assertRaises(ConflictError) as cm:
      ct.isChange('first', constants.ITEM_ADDED, 'Joe')
    self.assertEqual(ct.isChange('suffix', constants.ITEM_MODIFIED, 'Sr.'), 'suffix')
    self.assertEqual(ct.isChange('suffix', constants.ITEM_ADDED, 'Sr.'), 'suffix')
    with self.assertRaises(ConflictError) as cm:
      ct.isChange('mi', constants.ITEM_MODIFIED, 'F')
    self.assertEqual(ct.isChange('mi', constants.ITEM_ADDED, 'J'), None)
    with self.assertRaises(ConflictError) as cm:
      ct.isChange('tel-pager', constants.ITEM_MODIFIED, '+1-modified-value')
    self.assertEqual(ct.isChange('tel-pager', constants.ITEM_ADDED, '1234'), None)
    # TODO: HM. THIS SHOULDN'T BE VALID...
    self.assertEqual(ct.isChange('tel-pager', constants.ITEM_DELETED), None)

  #----------------------------------------------------------------------------
  def test_update_returnValue(self):
    base = 'add:first|mod:mi@vJ,surname@vSmith|del:tel-pager@v1234'
    ct = AttributeChangeTracker(base)
    self.assertEqual(ct.update('first', 'Joe', None), 'Joe')
    self.assertEqual(ct.update('first', 'Joe', 'Joe'), 'Joe')
    self.assertEqual(ct.update('tel-home', '1234', None), None)
    self.assertEqual(ct.update('tel-work', '1234', '3456'), '3456')
    self.assertEqual(ct.update('tel-other', None, '6789'), '6789')
    self.assertEqual(ct.update('suffix', None, 'Sr.'), 'Sr.')
    with self.assertRaises(ConflictError) as cm:
      ct.update('first', 'Joe', 'Joseph')
    with self.assertRaises(ConflictError) as cm:
      ct.update('mi', 'K', None)
    with self.assertRaises(ConflictError) as cm:
      ct.update('tel-pager', None, '0987')

  # #----------------------------------------------------------------------------
  # # TODO: commenting this out for now as it is not implemented!...
  # def test_nochange(self):
  #   # ensuring that change to field "y" as: "a" => "b" => "a" results
  #   # in a local no-change and allows a remote peer to change it... this
  #   # is a serious corner case, but is probably legit.
  #   ct = AttributeChangeTracker()
  #   ct.append('x', constants.ITEM_MODIFIED, 'a')
  #   ct.append('y', constants.ITEM_MODIFIED, 'a')
  #   ct.pushChangeSpec()
  #   ct.append('y', constants.ITEM_MODIFIED, 'b')
  #   ct.pushChangeSpec()
  #   self.assertEqual(ct.update('y', 'a', 'A'), 'A')

  #----------------------------------------------------------------------------
  def test_update_delete(self):
    ct = AttributeChangeTracker('add:first|mod:mi@vJ,surname@vSmith|del:tel-pager@v1234')
    self.assertEqual(ct.update('first', 'Joe', None), 'Joe')
    self.assertEqual(ct.update('tel-home', '1234', None), None)
    self.assertEqual(
      ct.getFullChangeSpec(),
      'add:first|mod:mi@vJ,surname@vSmith|del:tel-home@v1234,tel-pager@v1234')
    self.assertEqual(ct.getChangeSpec(), 'del:tel-home@v1234')

  #----------------------------------------------------------------------------
  def test_update_modify(self):
    ct = AttributeChangeTracker('add:first|mod:mi@vJ,surname@vSmith|del:tel-pager@v1234')
    self.assertEqual(ct.update('tel-home', '1234', '4321'), '4321')
    self.assertEqual(
      ct.getFullChangeSpec(),
      'add:first|mod:mi@vJ,surname@vSmith,tel-home@v1234|del:tel-pager@v1234')
    self.assertEqual(ct.getChangeSpec(), 'mod:tel-home@v1234')

  #----------------------------------------------------------------------------
  def test_update_add(self):
    ct = AttributeChangeTracker('add:first|mod:mi@vJ,surname@vSmith|del:tel-pager@v1234')
    self.assertEqual(ct.update('tel-home', None, '1234'), '1234')
    self.assertEqual(
      ct.getFullChangeSpec(),
      'add:first,tel-home|mod:mi@vJ,surname@vSmith|del:tel-pager@v1234')
    self.assertEqual(ct.getChangeSpec(), 'add:tel-home')

#------------------------------------------------------------------------------
class TestListChangeTracker(unittest.TestCase):

  maxDiff = None

  #----------------------------------------------------------------------------
  def test_changespec_gen_simple(self):
    ct = ListChangeTracker()
    # index: 0123456789
    # from:  ab cdef
    # to:    abXC eFY
    ct.append(2, constants.ITEM_ADDED)
    ct.append(3, constants.ITEM_MODIFIED, 'c')
    ct.append(4, constants.ITEM_DELETED, 'd')
    ct.append(6, constants.ITEM_MODIFIED, 'f')
    ct.append(7, constants.ITEM_ADDED)
    chk = '2:a,1:mc,1:dd,2:mf,1:a'
    self.assertEqual(str(ct), chk)

  #----------------------------------------------------------------------------
  def test_changespec_parser_roundtrip(self):
    cspec = '2:a,1:mc,1:dd,2:mf,1:a'
    ct = ListChangeTracker(cspec)
    self.assertEqual(str(ct), cspec)

  #----------------------------------------------------------------------------
  def test_changespec_gen_multi_byappend(self):
    # index: 0123456789
    # from:  ab cdef
    # to:    abXC eFY
    ct = ListChangeTracker()
    self.assertEqual(ct.baseline, [])
    self.assertEqual(ct.current, [])
    ct.append(2, constants.ITEM_ADDED)
    ct.append(3, constants.ITEM_MODIFIED, 'c')
    ct.append(4, constants.ITEM_DELETED, 'd')
    ct.append(6, constants.ITEM_MODIFIED, 'f')
    ct.append(7, constants.ITEM_ADDED)
    # note: accessing internals...
    self.assertEqual(ct.baseline, [])
    self.assertEqual(ct.current, [
      {'index': 2, 'ival': None, 'md5': False, 'op': 1},
      {'index': 3, 'ival': 'c', 'md5': False, 'op': 2},
      {'index': 4, 'ival': 'd', 'md5': False, 'op': 3},
      {'index': 6, 'ival': 'f', 'md5': False, 'op': 2},
      {'index': 7, 'ival': None, 'md5': False, 'op': 1},
      ])
    chk = '2:a,1:mc,1:dd,2:mf,1:a'
    self.assertEqual(str(ct), chk)
    # index: 0123456789
    # from:   abXCeFY
    # to:    ZabSCe Y
    ct.pushChangeSpec()
    self.assertEqual(ct.baseline, [
      {'index': 2, 'ival': None, 'md5': False, 'op': 1},
      {'index': 3, 'ival': 'c', 'md5': False, 'op': 2},
      {'index': 4, 'ival': 'd', 'md5': False, 'op': 3},
      {'index': 6, 'ival': 'f', 'md5': False, 'op': 2},
      {'index': 7, 'ival': None, 'md5': False, 'op': 1},
      ])
    ct.append(0, constants.ITEM_ADDED)
    ct.append(3, constants.ITEM_MODIFIED, 'X')
    ct.append(6, constants.ITEM_DELETED, 'F')
    self.assertEqual(ct.current, [
      {'index': 0, 'ival': None, 'md5': False, 'op': 1},
      {'index': 3, 'ival': 'X', 'md5': False, 'op': 2},
      {'index': 6, 'ival': 'F', 'md5': False, 'op': 3},
      ])
    chk = '0:a,3:a,1:mc,1:dd,2:df,1:a'
    self.assertEqual(str(ct), chk)
    # index: 0123456789
    # from:  ZabSCe Y
    # to:    Z  SCeTUV
    ct.pushChangeSpec()
    self.assertEqual(ct.baseline, [
      {'index': 0, 'ival': None, 'md5': False, 'op': 1},
      {'index': 3, 'ival': None, 'md5': False, 'op': 1},
      {'index': 4, 'ival': 'c', 'md5': False, 'op': 2},
      {'index': 5, 'ival': 'd', 'md5': False, 'op': 3},
      {'index': 7, 'ival': 'f', 'md5': False, 'op': 3},
      {'index': 8, 'ival': None, 'md5': False, 'op': 1},
      ])
    ct.append(1, constants.ITEM_DELETED, 'a')
    ct.append(2, constants.ITEM_DELETED, 'b')
    ct.append(6, constants.ITEM_ADDED)
    ct.append(7, constants.ITEM_MODIFIED, 'Y')
    ct.append(8, constants.ITEM_ADDED)
    self.assertEqual(ct.current, [
      {'index': 1, 'ival': 'a', 'md5': False, 'op': 3},
      {'index': 2, 'ival': 'b', 'md5': False, 'op': 3},
      {'index': 6, 'ival': None, 'md5': False, 'op': 1},
      {'index': 7, 'ival': 'Y', 'md5': False, 'op': 2},
      {'index': 8, 'ival': None, 'md5': False, 'op': 1},
      ])
    chk = '0:a,1:da,1:db,1:a,1:mc,1:dd,2:df,1:a,1:a,1:a'
    self.assertEqual(str(ct), chk)

  #----------------------------------------------------------------------------
  def test_changespec_gen_multi_byspecpush(self):
    ct = ListChangeTracker('2:a,1:mc,1:dd,2:mf,1:a')
    ct.pushChangeSpec('0:a,3:mX,3:dF')
    chk = '0:a,3:a,1:mc,1:dd,2:df,1:a'
    self.assertEqual(str(ct), chk)
    ct.pushChangeSpec('1:da,1:db,4:a,1:mY,1:a')
    chk = '0:a,1:da,1:db,1:a,1:mc,1:dd,2:df,1:a,1:a,1:a'
    self.assertEqual(str(ct), chk)

  #----------------------------------------------------------------------------
  def test_changespec_gen_multi_byspecone(self):
    # index: 0123456789A
    # from:   ab cdef
    # to:     abXC eF Y
    # to:    ZabSC e  Y
    # to:    Z  SC e TUV
    ct = ListChangeTracker(
      '2:a,1:mc,1:dd,2:mf,1:a'
      ';0:a,3:mX,3:dF'
      ';1:da,1:db,4:a,3:mY,1:a')
    chk = '0:a,1:da,1:db,1:a,1:mc,1:dd,2:df,1:a,1:a,2:mY,1:a'
    self.assertEqual(str(ct), chk)

  #----------------------------------------------------------------------------
  def test_changespec_cancelOut(self):
    # index: 0123456789A
    # from:  ab cd ef
    # to:    abXcdYef
    # to:     bXcd eF
    ct = ListChangeTracker(
      '2:a,3:a'
      ';0:da,5:dY,2:mf')
    chk = '0:da,2:a,4:mf'
    self.assertEqual(str(ct), chk)

  #----------------------------------------------------------------------------
  def test_conflict_simple_mod(self):
    # index: 0123456789
    # orig:  abcdef
    ct = ListChangeTracker('2:mc')
    self.assertEqual(ct.isChange(0, constants.ITEM_MODIFIED, 'A'), (0, None))
    self.assertEqual(ct.isChange(1, constants.ITEM_MODIFIED, 'B'), (1, None))
    self.assertEqual(ct.isChange(2, constants.ITEM_MODIFIED, 'c'), (None, None))
    with self.assertRaises(ConflictError) as cm:
      ct.isChange(2, constants.ITEM_MODIFIED, 'C')
    self.assertEqual(ct.isChange(4, constants.ITEM_MODIFIED, 'E'), (4, None))
    self.assertEqual(ct.isChange(4, constants.ITEM_ADDED, 'E'), (4, (4, 1)))
    with self.assertRaises(ConflictError) as cm:
      ct.isChange(2, constants.ITEM_DELETED)

  #----------------------------------------------------------------------------
  def test_conflict_simple_del(self):
    # index: 0123456789
    # orig:  abcdef
    # cur:   ab def
    # idx:   abdef
    ct = ListChangeTracker('2:dc')
    self.assertEqual(ct.isChange(0, constants.ITEM_MODIFIED, 'A'), (0, None))
    self.assertEqual(ct.isChange(1, constants.ITEM_MODIFIED, 'B'), (1, None))
    self.assertEqual(ct.isChange(2, constants.ITEM_ADDED, 'c'), (None, (2, 1)))
    self.assertEqual(ct.isChange(2, constants.ITEM_ADDED, 'C'), (2, (2, 1)))
    self.assertEqual(ct.isChange(2, constants.ITEM_MODIFIED, 'D'), (2, None))
    self.assertEqual(ct.isChange(3, constants.ITEM_MODIFIED, 'E'), (3, None))

  #----------------------------------------------------------------------------
  def test_multi_del(self):
    # index:  0123456789
    # orig:   abcdefghij
    # change: ab de ghij

    # local:  abdeghij
    # remote: abcdefgHij
    # ==> changes:
    #   2 add: c
    #   4 add: f
    #   5 mod: h => H

    ct = ListChangeTracker('2:dc,3:df')
    self.assertEqual(ct.isChange(2, constants.ITEM_ADDED, 'c'), (None, (2, 1)))
    self.assertEqual(ct.isChange(2, constants.ITEM_ADDED, 'C'), ((2, (2, 1))))
    self.assertEqual(ct.isChange(4, constants.ITEM_ADDED, 'f'), (None, (4, 1)))
    # note the caller is responsible for remembering to add 2 to the index...
    self.assertEqual(ct.isChange(5, constants.ITEM_MODIFIED, 'H'), (5, None))

  #----------------------------------------------------------------------------
  def test_merge_del_adjacent_add(self):
    # abcdefghi => a-cde-ghi
    #   (1, 0, 3, 'b', None)
    #   (5, 0, 3, 'f', None)

    # a-cde-ghi => abBcdefFXghi
    #   (1, 0, 1, None, 'b')
    #   (1, 1, 1, None, 'B')
    #   (4, 2, 1, None, 'f')
    #   (4, 3, 1, None, 'F')
    #   (4, 4, 1, None, 'X')

    ct = ListChangeTracker('1:db,4:df')
    self.assertEqual(
      ct.isChange(1, constants.ITEM_ADDED, 'b', token=None),
      (None, (1, 1)))
    self.assertEqual(
      ct.isChange(1, constants.ITEM_ADDED, 'B', token=(1, 1)),
      (1, (1, 1)))
    self.assertEqual(
      ct.isChange(4, constants.ITEM_ADDED, 'f', token=None),
      (None, (4, 1)))
    self.assertEqual(
      ct.isChange(4, constants.ITEM_ADDED, 'F', token=(4, 1)),
      (4, (4, 1)))
    self.assertEqual(
      ct.isChange(4, constants.ITEM_ADDED, 'X', token=(4, 1)),
      (4, (4, 1)))

  #----------------------------------------------------------------------------
  def test_merge_multi_add(self):

    # abcdefghi => aAbcdDefghHi
    #   (1, 0, 1, None, 'A')
    #   (4, 1, 1, None, 'D')
    #   (8, 2, 1, None, 'H')

    # aAb+cdDef+ghHi+ => a-bBcd-efFgh-iI
    #   (1, 0, 3, 'A', None)
    #   (3, 0, 1, None, 'B')
    #   (5, 1, 3, 'D', None)
    #   (8, 1, 1, None, 'F')
    #   (10, 2, 3, 'H', None)
    #   (12, 2, 1, None, 'I')

    # THE INDEX PASSED TO ListChangeTracker.isChange() DOES NOT INCLUDE:
    #   - local deletions
    #   - remote additions

    ct = ListChangeTracker('1:a,4:a,5:a')
    self.assertEqual(
      ct.isChange(1, constants.ITEM_DELETED, None, token=None)[0], None)
    self.assertEqual(
      ct.isChange(3, constants.ITEM_ADDED, 'B', token=None)[0], 3)
    self.assertEqual(
      ct.isChange(5, constants.ITEM_DELETED, None, token=None)[0], None)
    self.assertEqual(
      ct.isChange(8, constants.ITEM_ADDED, 'F', token=None)[0], 8)
    self.assertEqual(
      ct.isChange(10, constants.ITEM_DELETED, None, token=None)[0], None)
    self.assertEqual(
      ct.isChange(12, constants.ITEM_ADDED, 'I', token=None)[0], 12)

  #----------------------------------------------------------------------------
  def test_merge_multi_del(self):

    # abcdefghijklmnopqrs => a-cdef-hijklm-opqrs
    #   (1, 0, 3, 'b', None)
    #   (6, 0, 3, 'g', None)
    #   (13, 0, 3, 'n', None)

    # a+cdef+hijklm+opqrs => abc-efghi-klmnopq-s
    #   (1, 0, 1, None, 'b')
    #   (2, 1, 3, 'd', None)
    #   (5, 1, 1, None, 'g')
    #   (7, 2, 3, 'j', None)
    #   (11, 2, 1, None, 'n')
    #   (14, 3, 3, 'r', None)

    # ==> acefhiklmopqs

    # THE INDEX PASSED TO ListChangeTracker.isChange() DOES NOT INCLUDE:
    #   - local deletions
    #   - remote additions

    ct = ListChangeTracker('1:db,5:dg,7:dn')
    self.assertEqual(
      ct.isChange(1, constants.ITEM_ADDED, 'b', token=None)[0], None)
    self.assertEqual(
      ct.isChange(2, constants.ITEM_DELETED, None, token=None)[0], 2)
    self.assertEqual(
      ct.isChange(5, constants.ITEM_ADDED, 'g', token=None)[0], None)
    self.assertEqual(
      ct.isChange(7, constants.ITEM_DELETED, None, token=None)[0], 7)
    self.assertEqual(
      ct.isChange(11, constants.ITEM_ADDED, 'n', token=None)[0], None)
    self.assertEqual(
      ct.isChange(14, constants.ITEM_DELETED, None, token=None)[0], 14)

  #----------------------------------------------------------------------------
  def test_merge_consecutive_add(self):
    #  local               remote
    #  01234567890AB       01234567890ABCDEF
    #                      ab  cdef    gh  i
    #  ab  cdef  ghi       abABcd  efEFgh  i
    #  abABcdefEFghi       ab  cdCDef  ghGHi
    #
    #  abABcdCDefEFghGHi

    # abcdefghi => abABcdefEFghi
    #   (2, 0, 1, None, 'A')
    #   (2, 1, 1, None, 'B')
    #   (6, 2, 1, None, 'E')
    #   (6, 3, 1, None, 'F')

    # abABcd++efEFgh++i => abcdCDefghGHi
    #   (2, 0, 3, 'A', None)
    #   (3, 0, 3, 'B', None)
    #   (6, 0, 1, None, 'C')
    #   (6, 1, 1, None, 'D')
    #   (8, 2, 3, 'E', None)
    #   (9, 2, 3, 'F', None)
    #   (12, 2, 1, None, 'G')
    #   (12, 3, 1, None, 'H')

    ct = ListChangeTracker('2:a,1:a,5:a,1:a')
    self.assertEqual(
      ct.isChange(2, constants.ITEM_DELETED, None, token=None),
      (None, None))
    self.assertEqual(
      ct.isChange(3, constants.ITEM_DELETED, None, token=None),
      (None, None))
    self.assertEqual(
      ct.isChange(6, constants.ITEM_ADDED, 'C', token=None),
      (6, (6, 1)))
    self.assertEqual(
      ct.isChange(6, constants.ITEM_ADDED, 'D', token=(6, 1)),
      (6, (6, 2)))
    self.assertEqual(
      ct.isChange(8, constants.ITEM_DELETED, None, token=(6, 2)),
      (None, None))
    self.assertEqual(
      ct.isChange(9, constants.ITEM_DELETED, None, token=None),
      (None, None))
    self.assertEqual(
      ct.isChange(12, constants.ITEM_ADDED, 'G', token=None),
      (12, (12, 1)))
    self.assertEqual(
      ct.isChange(12, constants.ITEM_ADDED, 'H', token=(12, 1)),
      (12, (12, 2)))

  #----------------------------------------------------------------------------
  def test_merge_consecutive_del(self):
    # abcdefghijklmno (orig)
    # ab  efgh  klmno (local)
    # abcde  hijkl  o (remote)
    # abehklo         (result)

    # abcdefghijklmno => ab--efgh--klmno
    #   (2, 0, 3, 'c', None)
    #   (3, 0, 3, 'd', None)
    #   (8, 0, 3, 'i', None)
    #   (9, 0, 3, 'j', None)

    # ab++efgh++klmno => abcde--hijkl--o
    #   (2, 0, 1, None, 'c')
    #   (2, 1, 1, None, 'd')
    #   (3, 2, 3, 'f', None)
    #   (4, 2, 3, 'g', None)
    #   (6, 2, 1, None, 'i')
    #   (6, 3, 1, None, 'j')
    #   (8, 4, 3, 'm', None)
    #   (9, 4, 3, 'n', None)

    ct = ListChangeTracker('2:dc,1:dd,5:di,1:dj')
    self.assertEqual(
      ct.isChange(2, constants.ITEM_ADDED, 'c', token=None),
      (None, (2, 1)))
    self.assertEqual(
      ct.isChange(2, constants.ITEM_ADDED, 'd', token=(2, 1)),
      (None, (2, 2)))
    self.assertEqual(
      ct.isChange(3, constants.ITEM_DELETED, None, token=(2, 2)),
      (3, None))
    self.assertEqual(
      ct.isChange(4, constants.ITEM_DELETED, None, token=None),
      (4, None))
    self.assertEqual(
      ct.isChange(6, constants.ITEM_ADDED, 'i', token=None),
      (None, (6, 1)))
    self.assertEqual(
      ct.isChange(6, constants.ITEM_ADDED, 'j', token=(6, 1)),
      (None, (6, 2)))
    self.assertEqual(
      ct.isChange(8, constants.ITEM_DELETED, 'G', token=(8, 2)),
      (8, None))
    self.assertEqual(
      ct.isChange(9, constants.ITEM_DELETED, 'H', token=None),
      (9, None))

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
