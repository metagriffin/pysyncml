# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/06/03
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
from .note import NoteItem
from .. import constants, common

# kill logging
logging.disable(logging.CRITICAL)

#------------------------------------------------------------------------------
class TestNote(unittest.TestCase):

  #----------------------------------------------------------------------------
  def test_plain_load(self):
    note = NoteItem.loads('content', contentType=constants.TYPE_TEXT_PLAIN)
    self.assertEqual(note.name, 'content')
    self.assertEqual(note.body, 'content')

  #----------------------------------------------------------------------------
  def test_plain_dump(self):
    note = NoteItem(name='this note name', body='content')
    out = note.dumps(contentType=constants.TYPE_TEXT_PLAIN)
    self.assertEqual(out, 'content')

  #----------------------------------------------------------------------------
  def test_sifn_load(self):
    note = NoteItem.loads('<note><SIFVersion>1.1</SIFVersion><Subject>this note name</Subject><Body>content</Body></note>', contentType=constants.TYPE_SIF_NOTE)
    self.assertEqual(note.name, 'this note name')
    self.assertEqual(note.body, 'content')

  #----------------------------------------------------------------------------
  def test_sifn_dump(self):
    note = NoteItem(name='this note name', body='content')
    out = note.dumps(contentType=constants.TYPE_SIF_NOTE, version='1.1')
    self.assertEqual(out, '<note><SIFVersion>1.1</SIFVersion><Subject>this note name</Subject><Body>content</Body></note>')

  #----------------------------------------------------------------------------
  def test_sifn_ext_load(self):
    note = NoteItem.loads('<note><SIFVersion>1.1</SIFVersion><Subject>this note name</Subject><Body>content</Body><filename>this-note-name.txt</filename></note>', contentType=constants.TYPE_SIF_NOTE)
    self.assertEqual(note.name, 'this note name')
    self.assertEqual(note.body, 'content')
    self.assertEqual(note.extensions, dict(filename=['this-note-name.txt']))

  #----------------------------------------------------------------------------
  def test_sifn_ext_dump(self):
    note = NoteItem(name='this note name', body='content')
    note.addExtension('filename', 'this-note-name.txt')
    out = note.dumps(contentType=constants.TYPE_SIF_NOTE, version='1.1')
    self.assertEqual(out, '<note><SIFVersion>1.1</SIFVersion><Subject>this note name</Subject><Body>content</Body><filename>this-note-name.txt</filename></note>')

  #----------------------------------------------------------------------------
  def test_bad_contentType_load(self):
    vcard = '''BEGIN:VCARD
VERSION:3.0
PRODID:-//UnitTest//vCard 3.0//
UID:local:12345
END:VCARD
'''
    with self.assertRaises(common.InvalidContentType) as cm:
      NoteItem.loads(vcard, contentType=constants.TYPE_VCARD_V30)

  #----------------------------------------------------------------------------
  def test_bad_contentType_dump(self):
    note = NoteItem(name='this note name', body='content')
    with self.assertRaises(common.InvalidContentType) as cm:
      note.dumps(contentType=constants.TYPE_VCARD_V30)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
