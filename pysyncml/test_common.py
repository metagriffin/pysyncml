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

import unittest, re, six

from . import common, constants
from .common import adict

#------------------------------------------------------------------------------
class TestCommon(unittest.TestCase):

  maxDiff = None

  #----------------------------------------------------------------------------
  def test_fullClassname(self):
    self.assertEqual(
      common.fullClassname(self), 'pysyncml.test_common.TestCommon')

  #----------------------------------------------------------------------------
  def test_indent(self):
    buf = six.StringIO()
    out = common.IndentStream(buf, '>>')
    out.write('hi')
    self.assertMultiLineEqual(buf.getvalue(), '>>hi')
    out.write(', there!')
    out.write('\nhow are you?\n')
    self.assertMultiLineEqual(buf.getvalue(), '>>hi, there!\n>>how are you?\n')

  #----------------------------------------------------------------------------
  def test_indent_print(self):
    buf = six.StringIO()
    out = common.IndentStream(buf, '>>')
    out.write('hi')
    self.assertMultiLineEqual(buf.getvalue(), '>>hi')
    print >>out, ', there!'
    print >>out, 'how are you?'
    self.assertMultiLineEqual(buf.getvalue(), '>>hi, there!\n>>how are you?\n')

  #----------------------------------------------------------------------------
  def test_version(self):
    # ensure that the version is always "MAJOR.MINOR.SOMETHING"
    self.assertTrue(re.match(r'^[0-9]+\.[0-9]+\.[0-9a-z.-]*$', common.version)
                    is not None)

  #----------------------------------------------------------------------------
  def test_describeStats(self):
    buf = six.StringIO()
    stats = dict(note=adict(
      mode=constants.SYNCTYPE_TWO_WAY,conflicts=0,merged=0,
      hereAdd=10,hereMod=0,hereDel=0,hereErr=0,
      peerAdd=0,peerMod=0,peerDel=2,peerErr=0))
    common.describeStats(stats, buf)
    chk = '''
+--------+------+-----------------------+-----------------------+-----------+
|        |      |         Local         |        Remote         | Conflicts |
| Source | Mode | Add | Mod | Del | Err | Add | Mod | Del | Err | Col | Mrg |
+--------+------+-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
|   note |  <>  |  10 |  -  |  -  |  -  |  -  |  -  |   2 |  -  |  -  |  -  |
+--------+------+-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
|                  10 local changes and 2 remote changes.                   |
+---------------------------------------------------------------------------+
'''.lstrip()
    self.assertMultiLineEqual(buf.getvalue(), chk)

  #----------------------------------------------------------------------------
  def test_describeStats_noTotals(self):
    buf = six.StringIO()
    stats = dict(note=adict(
      mode=constants.SYNCTYPE_TWO_WAY,conflicts=0,merged=0,
      hereAdd=10,hereMod=0,hereDel=0,hereErr=0,
      peerAdd=0,peerMod=0,peerDel=2,peerErr=0))
    common.describeStats(stats, buf, totals=False)
    chk = '''
+--------+------+-----------------------+-----------------------+-----------+
|        |      |         Local         |        Remote         | Conflicts |
| Source | Mode | Add | Mod | Del | Err | Add | Mod | Del | Err | Col | Mrg |
+--------+------+-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
|   note |  <>  |  10 |  -  |  -  |  -  |  -  |  -  |   2 |  -  |  -  |  -  |
+--------+------+-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
'''.lstrip()
    self.assertMultiLineEqual(buf.getvalue(), chk)

  #----------------------------------------------------------------------------
  def test_describeStats_title(self):
    buf = six.StringIO()
    stats = dict(note=adict(
      mode=constants.SYNCTYPE_TWO_WAY,conflicts=0,merged=0,
      hereAdd=10,hereMod=0,hereDel=0,hereErr=0,
      peerAdd=0,peerMod=0,peerDel=2,peerErr=0))
    common.describeStats(stats, buf, title='Synchronization Summary')
    chk = '''
+---------------------------------------------------------------------------+
|                          Synchronization Summary                          |
+--------+------+-----------------------+-----------------------+-----------+
|        |      |         Local         |        Remote         | Conflicts |
| Source | Mode | Add | Mod | Del | Err | Add | Mod | Del | Err | Col | Mrg |
+--------+------+-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
|   note |  <>  |  10 |  -  |  -  |  -  |  -  |  -  |   2 |  -  |  -  |  -  |
+--------+------+-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
|                  10 local changes and 2 remote changes.                   |
+---------------------------------------------------------------------------+
'''.lstrip()
    self.assertMultiLineEqual(buf.getvalue(), chk)

  #----------------------------------------------------------------------------
  def test_describeStats_errors(self):
    buf = six.StringIO()
    stats = dict(note=adict(
      mode=constants.SYNCTYPE_TWO_WAY,conflicts=0,merged=0,
      hereAdd=10,hereMod=0,hereDel=0,hereErr=1,
      peerAdd=0,peerMod=0,peerDel=1,peerErr=2))
    common.describeStats(stats, buf, title='Synchronization Summary')
    chk = '''
+---------------------------------------------------------------------------+
|                          Synchronization Summary                          |
+--------+------+-----------------------+-----------------------+-----------+
|        |      |         Local         |        Remote         | Conflicts |
| Source | Mode | Add | Mod | Del | Err | Add | Mod | Del | Err | Col | Mrg |
+--------+------+-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
|   note |  <>  |  10 |  -  |  -  |   1 |  -  |  -  |   1 |   2 |  -  |  -  |
+--------+------+-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
|              10 local changes, 1 remote change and 3 errors.              |
+---------------------------------------------------------------------------+
'''.lstrip()
    self.assertMultiLineEqual(buf.getvalue(), chk)

  #----------------------------------------------------------------------------
  def test_describeStats_multiwide(self):
    buf = six.StringIO()
    stats = dict(note=adict(
      mode=constants.SYNCTYPE_SLOW_SYNC,conflicts=0,merged=0,
      hereAdd=1308,hereMod=0,hereDel=2,hereErr=0,
      peerAdd=0,peerMod=0,peerDel=0,peerErr=0),
                 contacts=adict(
      mode=constants.SYNCTYPE_REFRESH_FROM_SERVER,conflicts=0,merged=0,
      hereAdd=0,hereMod=0,hereDel=0,hereErr=0,
      peerAdd=10387,peerMod=0,peerDel=0,peerErr=0))
    common.describeStats(stats, buf)
    chk = '''
+----------+------+-------------------------+--------------------------+-----------+
|          |      |          Local          |          Remote          | Conflicts |
|   Source | Mode |  Add  | Mod | Del | Err |  Add   | Mod | Del | Err | Col | Mrg |
+----------+------+-------+-----+-----+-----+--------+-----+-----+-----+-----+-----+
| contacts |  <=  |   -   |  -  |  -  |  -  | 10,387 |  -  |  -  |  -  |  -  |  -  |
|     note |  SS  | 1,308 |  -  |   2 |  -  |   -    |  -  |  -  |  -  |  -  |  -  |
+----------+------+-------+-----+-----+-----+--------+-----+-----+-----+-----+-----+
|                  1,310 local changes and 10,387 remote changes.                  |
+----------------------------------------------------------------------------------+
'''.lstrip()
    self.assertMultiLineEqual(buf.getvalue(), chk)

  #----------------------------------------------------------------------------
  def test_describeStats_titleAndTotals(self):
    buf = six.StringIO()
    stats = dict(note=adict(
      mode=constants.SYNCTYPE_SLOW_SYNC,conflicts=0,merged=0,
      hereAdd=1308,hereMod=0,hereDel=2,hereErr=0,
      peerAdd=0,peerMod=0,peerDel=0,peerErr=0),
                 contacts=adict(
      mode=constants.SYNCTYPE_REFRESH_FROM_SERVER,conflicts=0,merged=0,
      hereAdd=0,hereMod=0,hereDel=0,hereErr=0,
      peerAdd=10387,peerMod=0,peerDel=0,peerErr=0))
    common.describeStats(stats, buf, title='Synchronization Summary', details=False)
    chk = '''
+------------------------------------------------+
|            Synchronization Summary             |
| 1,310 local changes and 10,387 remote changes. |
+------------------------------------------------+
'''.lstrip()
    self.assertMultiLineEqual(buf.getvalue(), chk)

  #----------------------------------------------------------------------------
  def test_describeStats_totals(self):
    buf = six.StringIO()
    stats = dict(note=adict(
      mode=constants.SYNCTYPE_SLOW_SYNC,conflicts=0,merged=0,
      hereAdd=1308,hereMod=0,hereDel=2,hereErr=0,
      peerAdd=0,peerMod=0,peerDel=0,peerErr=0),
                 contacts=adict(
      mode=constants.SYNCTYPE_REFRESH_FROM_SERVER,conflicts=0,merged=0,
      hereAdd=0,hereMod=0,hereDel=0,hereErr=0,
      peerAdd=10387,peerMod=0,peerDel=0,peerErr=0))
    common.describeStats(stats, buf, details=False)
    chk = '''
+------------------------------------------------+
| 1,310 local changes and 10,387 remote changes. |
+------------------------------------------------+
'''.lstrip()
    self.assertMultiLineEqual(buf.getvalue(), chk)
    stats['note'].merged    = 3
    stats['note'].conflicts = 2
    stats['note'].hereErr   = 2
    buf = six.StringIO()
    common.describeStats(stats, buf, details=False)
    chk = '''
+------------------------------------------------------------------------------------+
| 1,310 local changes, 10,387 remote changes and 2 errors: 3 merges and 2 conflicts. |
+------------------------------------------------------------------------------------+
'''.lstrip()
    self.assertMultiLineEqual(buf.getvalue(), chk)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
