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

import unittest, re
import xml.etree.ElementTree as ET
from StringIO import StringIO as sio
from . import ctype, constants

#------------------------------------------------------------------------------
class TestCtype(unittest.TestCase):

  maxDiff = None

  #----------------------------------------------------------------------------
  def test_nameOverride(self):
    ct = ctype.ContentTypeInfo('text/plain', '1.0', preferred=True)
    out = ET.tostring(ct.toSyncML('CT'))
    chk = '<CT><CTType>text/plain</CTType><VerCT>1.0</VerCT></CT>'
    self.assertEqual(out, chk)

  #----------------------------------------------------------------------------
  def test_multiVers_multiVerCT(self):
    ct = ctype.ContentTypeInfo('text/plain', ['1.0', '1.1'], preferred=True)
    out = ET.tostring(ct.toSyncML())
    chk = '<ContentType><CTType>text/plain</CTType><VerCT>1.0</VerCT><VerCT>1.1</VerCT></ContentType>'
    self.assertEqual(out, chk)

  #----------------------------------------------------------------------------
  def test_multiVers_uniqueVerCT(self):
    ct = ctype.ContentTypeInfo('text/plain', ['1.0', '1.1'], preferred=True)
    xnode = ET.Element('C')
    for n in ct.toSyncML('CT', uniqueVerCt=True):
      xnode.append(n)
    out = ET.tostring(xnode)
    chk = '<C><CT><CTType>text/plain</CTType><VerCT>1.0</VerCT></CT><CT><CTType>text/plain</CTType><VerCT>1.1</VerCT></CT></C>'
    self.assertEqual(out, chk)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
