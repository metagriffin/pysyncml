# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/05/13
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
The ``pysyncml.agents.file`` module provides helper routines and classes to
deal with SyncML file and folder object types.
'''

from . import base
from .. import constants, ctype
from ..items import FileItem, FolderItem

#------------------------------------------------------------------------------
class BaseFileAgent(base.Agent):

  #----------------------------------------------------------------------------
  def __init__(self, *args, **kw):
    super(BaseFileAgent, self).__init__(*args, **kw)
    self.hierarchicalSync = True
    self.contentTypes = [
      ctype.ContentTypeInfo(constants.TYPE_OMADS_FILE, '1.2', preferred=True),
      ctype.ContentTypeInfo(constants.TYPE_OMADS_FOLDER, '1.2'),
      ]

  #----------------------------------------------------------------------------
  def loadItem(self, stream, contentType=None, version=None):
    if contentType is not None:
      if ctype.getBaseType(contentType) == constants.TYPE_OMADS_FOLDER:
        return FolderItem.load(stream, contentType, version)
    return FileItem.load(stream, contentType, version)

  #----------------------------------------------------------------------------
  def dumpItem(self, item, stream, contentType=None, version=None):
    # todo: is this "getItem" really necessary?... it is for paranoia
    #       purposes to ensure that the object is actually a FileItem.
    item = self.getItem(item.id)
    if contentType is not None and \
       not ctype.getBaseType(contentType) == constants.TYPE_OMADS_FOLDER and \
       not ctype.getBaseType(contentType) == constants.TYPE_OMADS_FILE:
      raise common.InvalidContentType('cannot serialize file item to "%s"' % (contentType,))
    if isinstance(item, FolderItem):
      # todo: this is a bit of a hack... i'm not really sure how to
      #       resolve it. the rest of pysyncml is geared toward an agent
      #       only being able to handle a single content-type...
      return item.dump(stream, constants.TYPE_OMADS_FOLDER, version)
    return item.dump(stream, constants.TYPE_OMADS_FILE, version)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
