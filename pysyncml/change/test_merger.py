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
from StringIO import StringIO as sio
from .. import common, constants, test_helpers
from ..common import adict, ConflictError
from .merger import *

#------------------------------------------------------------------------------
def s(string, sep=' '):
  return sep.join(string)

#------------------------------------------------------------------------------
def S(string, sep=' '):
  return ''.join(string.split(sep))

#------------------------------------------------------------------------------
class TestTextMerger(unittest.TestCase, test_helpers.MultiLineEqual):

  maxDiff = None

  # #----------------------------------------------------------------------------
  # def test_show(self):
  #   # abcdefghijklmno (orig)
  #   # ab  efgh  klmno (local)
  #   # abcde  hijkl  o (remote)
  #   tm = TextMerger(False, None)
  #   for change in tm._getChangeSets('acdeghi', 'abBcdefFXghi'):
  #     print change
  #   print tm.pushChange(s('abcdefghi'), s('acdeghi')).getChangeSpec()
  #   raise NotImplementedError

  #----------------------------------------------------------------------------
  def test_internal_changeSets_add(self):
    #  ab  cdef    gh  i (orig)
    #  abABcd  efEFgh  i (local)
    #  ab  cdCDef  ghGHi (remote)
    tm = TextMerger(False, None)
    self.assertEqual(
      [
        (2, 0, 1, None, 'A'),
        (2, 1, 1, None, 'B'),
        (6, 2, 1, None, 'E'),
        (6, 3, 1, None, 'F'),
       ],
      list(tm._getChangeSets('abcdefghi', 'abABcdefEFghi')))
    self.assertEqual(
      [
        (2, 0, 3, 'A', None),
        (3, 0, 3, 'B', None),
        (6, 0, 1, None, 'C'),
        (6, 1, 1, None, 'D'),
        (8, 2, 3, 'E', None),
        (9, 2, 3, 'F', None),
        (12, 2, 1, None, 'G'),
        (12, 3, 1, None, 'H'),
       ],
      list(tm._getChangeSets('abABcdefEFghi', 'abcdCDefghGHi')))

  #----------------------------------------------------------------------------
  def test_internal_changeSets_del(self):
    # abcdefghijklmno (orig)
    # ab  efgh  klmno (local)
    # abcde  hijkl  o (remote)
    tm = TextMerger(False, None)
    self.assertEqual(
      [
        (2, 0, 3, 'c', None),
        (3, 0, 3, 'd', None),
        (8, 0, 3, 'i', None),
        (9, 0, 3, 'j', None),
       ],
      list(tm._getChangeSets('abcdefghijklmno', 'abefghklmno')))
    self.assertEqual(
      [
        (2, 0, 1, None, 'c'),
        (2, 1, 1, None, 'd'),
        (3, 2, 3, 'f', None),
        (4, 2, 3, 'g', None),
        (6, 2, 1, None, 'i'),
        (6, 3, 1, None, 'j'),
        (8, 4, 3, 'm', None),
        (9, 4, 3, 'n', None),
       ],
      list(tm._getChangeSets('abefghklmno', 'abcdehijklo')))
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdefghijklmno'), s('abefghklmno')).getChangeSpec()
    self.assertEqual('2:dc,1:dd,5:di,1:dj', cspec)

  #----------------------------------------------------------------------------
  def test_internal_changeSets_combined(self):
    tm = TextMerger(True, None)
    self.assertEqual(
      [
        (2, 0, 2, 'line 2: * changed from "that"', 'line 2: that'),
        (5, 0, 2, 'line 5: bingo', 'line 5: * changed from "bingo"'),
        (6, 0, 1, None, 'line 5.1: * added one line'),
        (6, 1, 1, None, 'line 5.2: * added a second line'),
      ],
      list(tm._getChangeSets('''
line 1: this
line 2: * changed from "that"
line 3: foo
line 4: bar
line 5: bingo
line 6: star
line 7: done.
'''.split('\n'),'''
line 1: this
line 2: that
line 3: foo
line 4: bar
line 5: * changed from "bingo"
line 5.1: * added one line
line 5.2: * added a second line
line 6: star
line 7: done.
'''.split('\n'))))

  #----------------------------------------------------------------------------
  def test_changespec_add(self):
    tm = TextMerger(False, None)
    out = tm.pushChange(s('abcdef'), s('aABbcDdef')).getChangeSpec()
    chk = '1:a,1:a,3:a'
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_changespec_mod(self):
    tm = TextMerger(False, None)
    out = tm.pushChange(s('abcdef'), s('abCDef')).getChangeSpec()
    chk = '2:mc,1:md'
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_changespec_del(self):
    tm = TextMerger(False, None)
    out = tm.pushChange(s('abcdef'), s('abef')).getChangeSpec()
    chk = '2:dc,1:dd'
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_changespec_mixedReplaceDelete(self):
    tm = TextMerger(False, None)
    out = tm.pushChange(s('abcdef'), s('abCef')).getChangeSpec()
    chk = '2:mc,1:dd'
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_changespec_mixedReplaceInsert(self):
    tm = TextMerger(False, None)
    out = tm.pushChange(s('abcdef'), s('abCXYef')).getChangeSpec()
    chk = '2:mc,1:md,1:a'
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_simple_modify(self):
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdef'), s('abCdef')).getChangeSpec()
    tm = TextMerger(False, cspec)
    out = tm.mergeChanges(s('abCdef'), s('abcdEf'))
    chk = s('abCdEf')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_simple_mod_del(self):
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdef'), s('abCdef')).getChangeSpec()
    tm = TextMerger(False, cspec)
    out = tm.mergeChanges(s('abCdef'), s('abcdf'))
    chk = s('abCdf')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_simple_del_mod(self):
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdef'), s('acdef')).getChangeSpec()
    chk = '1:db'
    self.assertEqual(chk, cspec)
    tm  = TextMerger(False, cspec)
    out = tm.mergeChanges(s('acdef'), s('abcdef'))
    chk = s('acdef')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_simple_del_mod_2(self):
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('defghi'), s('dfghi')).getChangeSpec()
    chk = '1:de'
    self.assertEqual(chk, cspec)
    tm  = TextMerger(False, cspec)
    out = tm.mergeChanges(s('dfghi'), s('defGhi'))
    chk = s('dfGhi')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_simple_add(self):
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdef'), s('abCdef')).getChangeSpec()
    tm = TextMerger(False, cspec)
    out = tm.mergeChanges(s('abCdef'), s('abcdeXf'))
    chk = s('abCdeXf')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_simple_multiadd(self):
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdefghi'), s('abcdefghiX')).getChangeSpec()
    tm  = TextMerger(False, cspec)
    out = tm.mergeChanges(s('abcdefghiX'), s('abcdCDefghGHi'))
    chk = s('abcdCDefghGHiX')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_multiple_add(self):
    #  local               remote
    #  01234567890AB       01234567890ABCDEF
    #                      ab  cdef    gh  i
    #  ab  cdef  ghi       abABcd  efEFgh  i
    #  abABcdefEFghi       ab  cdCDef  ghGHi
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdefghi'), s('abABcdefEFghi')).getChangeSpec()
    tm  = TextMerger(False, cspec)
    out = tm.mergeChanges(s('abABcdefEFghi'), s('abcdCDefghGHi'))
    chk = s('abABcdCDefEFghGHi')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_multiple_del(self):
    # abcdefghijklmno
    # ab  efgh  klmno
    # abcde  hijkl  o
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdefghijklmno'), s('abefghklmno')).getChangeSpec()
    tm  = TextMerger(False, cspec)
    out = tm.mergeChanges(s('abefghklmno'), s('abcdehijklo'))
    chk = s('abehklo')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_multiple(self):
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdefghi'), s('abcABCdefghDi')).getChangeSpec()
    chk = '3:a,1:a,1:a,6:a'
    self.assertEqual(chk, cspec)
    tm  = TextMerger(False, cspec)
    out = tm.mergeChanges(s('abcABCdefghDi'), s('abcdeWXYfghiZ'))
    chk = s('abcABCdeWXYfghDiZ')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_multiple(self):
    tm = TextMerger(False, None)
    cspec = tm.pushChange(s('abcdefghi'), s('adefghi')).getChangeSpec()
    tm  = TextMerger(False, cspec)
    out = tm.mergeChanges(s('adefghi'), s('abcdefXghYi'))
    chk = s('adefXghYi')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_complex(self):
    tm = TextMerger(True, None)
    cspec = tm.pushChange('''
line 1: this
line 2: that
line 3: foo
line 4: bar
line 5: bingo
line 6: star
line 7: done.
''','''
line 1: this
line 2: * changed from "that"
line 3: foo
line 4: bar
line 5: bingo
line 6: star
line 7: done.
''').getChangeSpec()
    tm  = TextMerger(True, cspec)
    out = tm.mergeChanges('''
line 1: this
line 2: * changed from "that"
line 3: foo
line 4: bar
line 5: bingo
line 6: star
line 7: done.
''','''
line 1: this
line 2: that
line 3: foo
line 4: bar
line 5: * changed from "bingo"
line 5.1: * added one line
line 5.2: * added a second line
line 6: star
line 7: done.
''')
    chk = '''
line 1: this
line 2: * changed from "that"
line 3: foo
line 4: bar
line 5: * changed from "bingo"
line 5.1: * added one line
line 5.2: * added a second line
line 6: star
line 7: done.
'''
    self.assertMultiLineEqual(chk, out)

#------------------------------------------------------------------------------
class TestTextMergerFactory(unittest.TestCase, test_helpers.MultiLineEqual):

  maxDiff = None

  #----------------------------------------------------------------------------
  def test_detect(self):
    tm = TextMergerFactory(False).newMerger()
    out = tm.pushChange(s('abcdef'), s('abCXYef')).getChangeSpec()
    chk = '2:mc,1:md,1:a'
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge(self):
    tmf = TextMergerFactory(False)
    tm  = tmf.newMerger()
    cspec = tm.pushChange(s('abcdef'), s('abCdef')).getChangeSpec()
    tm  = tmf.newMerger(cspec)
    out = tm.mergeChanges(s('abCdef'), s('bcdeXf'))
    chk = s('bCdeXf')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_sameChange(self):
    tmf = TextMergerFactory(False)
    tm  = tmf.newMerger()
    cspec = tm.pushChange(s('abcdef'), s('abCdef')).getChangeSpec()
    tm  = tmf.newMerger(cspec)
    out = tm.mergeChanges(s('abCdef'), s('bCdeXf'))
    chk = s('bCdeXf')
    self.assertEqual(chk, out)

  #----------------------------------------------------------------------------
  def test_merge_conflict(self):
    tmf = TextMergerFactory(False)
    tm  = tmf.newMerger()
    cspec = tm.pushChange(s('abcdef'), s('abCdef')).getChangeSpec()
    tm  = tmf.newMerger(cspec)
    self.assertRaises(ConflictError, tm.mergeChanges, s('abCdef'), s('bZdeXf'))

#------------------------------------------------------------------------------
class TestCompositeMerger(unittest.TestCase, test_helpers.MultiLineEqual):

  maxDiff = None

  #----------------------------------------------------------------------------
  def test_textonly_generate(self):
    factory = CompositeMergerFactory(default=TextMergerFactory(False), sharedDefault=False)
    m = factory.newMerger()
    m.pushChange('text1', s('abc'), s('aBc'))
    m.pushChange('text2', s('def'), s('ef'))
    cspec = m.getChangeSpec()
    chk = 'text1=1%3Amb&text2=0%3Add'
    self.assertEqual(chk, cspec)

  #----------------------------------------------------------------------------
  def test_textonly_merge(self):
    factory = CompositeMergerFactory(default=TextMergerFactory(False), sharedDefault=False)
    m = factory.newMerger('text1=1%3Amb&text2=1%3Ade')
    self.assertEqual('a B c', m.mergeChanges('text1', 'a B c', 'a b c'))
    self.assertEqual('d f G h i', m.mergeChanges('text2', 'd f g h i', 'd e f G h i'))

  #----------------------------------------------------------------------------
  def test_textonly_conflict(self):
    factory = CompositeMergerFactory(default=TextMergerFactory(False), sharedDefault=False)
    m = factory.newMerger('text1=1%3Amb&text2=0%3Add')
    self.assertRaises(ConflictError, m.mergeChanges, 'text1', 'a B c', 'd e f')

  #----------------------------------------------------------------------------
  def test_generate(self):
    factory = CompositeMergerFactory(mergers=dict(body=TextMergerFactory(False)))
    m = factory.newMerger()
    m.pushChange('name', 'foo', 'bar')
    m.pushChange('body', 'a b c', 'a c')
    cspec = m.getChangeSpec()
    chk = 'mod%3Aname%40vfoo&body=1%3Adb'
    self.assertEqual(chk, cspec)

  #----------------------------------------------------------------------------
  def test_merge(self):
    factory = CompositeMergerFactory(mergers=dict(body=TextMergerFactory(False)))
    m = factory.newMerger('mod%3Aname%40vfoo&body=1%3Adb')
    self.assertEqual('bar', m.mergeChanges('name', 'bar', 'foo'))
    self.assertEqual('a c F', m.mergeChanges('body', 'a c', 'a b c F'))

  #----------------------------------------------------------------------------
  def test_merge_same(self):
    factory = CompositeMergerFactory(mergers=dict(body=TextMergerFactory(False)))
    m = factory.newMerger('mod%3Aname%40vfoo&body=1%3Amb')
    self.assertEqual('a B c D', m.mergeChanges('body', 'a B c', 'a B c D'))

  #----------------------------------------------------------------------------
  def test_merge_conflict_attr(self):
    factory = CompositeMergerFactory(mergers=dict(body=TextMergerFactory(False)))
    m = factory.newMerger('mod%3Aname%40vfoo&body=1%3Adb')
    self.assertRaises(ConflictError, m.mergeChanges, 'name', 'bar', 'fig')

  #----------------------------------------------------------------------------
  def test_merge_conflict_text(self):
    factory = CompositeMergerFactory(mergers=dict(body=TextMergerFactory(False)))
    m = factory.newMerger('mod%3Aname%40vfoo&body=1%3Amb')
    self.assertRaises(ConflictError, m.mergeChanges, 'body', 'a B c', 'a X c')

  #----------------------------------------------------------------------------
  def test_kwarg(self):
    factory = CompositeMergerFactory(body=TextMergerFactory(False))
    m = factory.newMerger('mod%3Aname%40vfoo&body=1%3Adb')
    self.assertEqual('bar', m.mergeChanges('name', 'bar', 'foo'))
    self.assertEqual('a c F', m.mergeChanges('body', 'a c', 'a b c F'))

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
