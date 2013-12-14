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
from . import codec, constants

#------------------------------------------------------------------------------
class TestCodec(unittest.TestCase):

  #----------------------------------------------------------------------------
  def test_encode_utf8(self):
    uni = u'\u30c6\u30b9\u30c8'
    raw = 'テスト'
    self.assertEqual(raw.decode('utf-8'), uni)
    xdoc = ET.Element('root')
    xdoc.text = uni
    contentType, data = codec.Codec.factory(constants.CODEC_XML).encode(xdoc)
    self.assertEqual(contentType, 'application/vnd.syncml+xml; charset=UTF-8')
    # TODO: determine which output i actually want...
    self.assertEqual(data, '<root>&#12486;&#12473;&#12488;</root>')
    #self.assertEqual(data, '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n<root>\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88</root>')

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
