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
from .folder import FolderItem

# kill logging
logging.disable(logging.CRITICAL)

#------------------------------------------------------------------------------
class TestFolder(unittest.TestCase):

  #----------------------------------------------------------------------------
  def test_dump_simple(self):
    fi = FolderItem(name='foldername')
    self.assertEqual(
      ('application/vnd.omads-folder+xml', '1.2',
       '<Folder><name>foldername</name></Folder>'),
      fi.dumps())

  #----------------------------------------------------------------------------
  def test_load_simple(self):
    fi  = FolderItem.loads('<Folder><name>foldername</name></Folder>')
    chk = FolderItem(name='foldername')
    self.assertEqual(chk, fi)

  #----------------------------------------------------------------------------
  def test_dump_attributes(self):
    fi = FolderItem(name='n', hidden=True, system=False)
    self.assertEqual(
      ('application/vnd.omads-folder+xml', '1.2',
       '<Folder><name>n</name><attributes><h>true</h><s>false</s></attributes></Folder>'),
      fi.dumps())

  #----------------------------------------------------------------------------
  def test_load_attributes(self):
    fi  = FolderItem.loads('<Folder><name>n</name><attributes><h>true</h><s>false</s></attributes></Folder>')
    chk = FolderItem(name='n', hidden=True, system=False)
    self.assertEqual(chk, fi)

  #----------------------------------------------------------------------------
  def test_dump_dates(self):
    fi = FolderItem(name='n', created=1234567890)
    self.assertEqual(
      ('application/vnd.omads-folder+xml', '1.2',
       '<Folder><name>n</name><created>20090213T233130Z</created></Folder>'),
      fi.dumps())

  #----------------------------------------------------------------------------
  def test_load_dates(self):
    fi  = FolderItem.loads('<Folder><name>n</name><created>20090213T233130Z</created></Folder>')
    chk = FolderItem(name='n', created=1234567890)
    self.assertEqual(chk, fi)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
