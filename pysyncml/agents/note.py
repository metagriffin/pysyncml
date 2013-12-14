# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/05/20
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
The ``pysyncml.agents.note`` module provides helper routines and classes to
deal with SyncML note and memo object types.
'''

from . import base
from .. import constants, ctype
from ..items.note import NoteItem

#------------------------------------------------------------------------------
class BaseNoteAgent(base.Agent):

  #----------------------------------------------------------------------------
  def __init__(self, *args, **kw):
    super(BaseNoteAgent, self).__init__(*args, **kw)
    self.contentTypes = [
      ctype.ContentTypeInfo(constants.TYPE_SIF_NOTE, '1.1', preferred=True),
      ctype.ContentTypeInfo(constants.TYPE_SIF_NOTE, '1.0'),
      ctype.ContentTypeInfo(constants.TYPE_TEXT_PLAIN, ['1.1', '1.0']),
      ]

  #----------------------------------------------------------------------------
  def loadItem(self, stream, contentType=None, version=None):
    return NoteItem.load(stream, contentType, version)

  #----------------------------------------------------------------------------
  def dumpItem(self, item, stream, contentType=None, version=None):
    # todo: is this "getItem" really necessary?... it is for paranoia
    #       purposes to ensure that the object is actually a NoteItem.
    return self.getItem(item.id).dump(stream, contentType, version)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
