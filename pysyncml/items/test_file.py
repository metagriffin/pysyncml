# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/05/19
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

import unittest, logging
from .file import FileItem

# kill logging
logging.disable(logging.CRITICAL)

#------------------------------------------------------------------------------
class TestFile(unittest.TestCase):

  #----------------------------------------------------------------------------
  def test_dump_simple(self):
    fi = FileItem(name='filename.ext', body='some text.\n')
    self.assertEqual(
      ('application/vnd.omads-file+xml', '1.2',
       '<File><name>filename.ext</name><body>some text.\n</body></File>'),
      fi.dumps())

  #----------------------------------------------------------------------------
  def test_load_simple(self):
    fi  = FileItem.loads('<File><name>filename.ext</name><body>some text.\n</body></File>')
    chk = FileItem(name='filename.ext', body='some text.\n')
    self.assertEqual(chk, fi)

  #----------------------------------------------------------------------------
  def test_dump_attributes(self):
    fi = FileItem(name='n', hidden=True, system=False)
    self.assertEqual(
      ('application/vnd.omads-file+xml', '1.2',
       '<File><name>n</name><attributes><h>true</h><s>false</s></attributes></File>'),
      fi.dumps())

  #----------------------------------------------------------------------------
  def test_load_attributes(self):
    fi  = FileItem.loads('<File><name>n</name><attributes><h>true</h><s>false</s></attributes></File>')
    chk = FileItem(name='n', hidden=True, system=False)
    self.assertEqual(chk, fi)

  #----------------------------------------------------------------------------
  def test_dump_dates(self):
    fi = FileItem(id='0', name='n', created=1234567890)
    self.assertEqual(
      ('application/vnd.omads-file+xml', '1.2',
       '<File><name>n</name><created>20090213T233130Z</created></File>'),
      fi.dumps())

  #----------------------------------------------------------------------------
  def test_load_dates(self):
    fi  = FileItem.loads('<File><name>n</name><created>20090213T233130Z</created></File>')
    chk = FileItem(name='n', created=1234567890)
    self.assertEqual(chk, fi)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
