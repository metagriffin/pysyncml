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
The ``pysyncml.items.folder`` module defines the abstract interface to an
OMA DS Folder object via the :class:`pysyncml.items.folder.FolderItem` class.
'''

import os
import xml.etree.ElementTree as ET
from .base import Item, Ext
from .. import constants, common, ctype
from .file import FileItem

#------------------------------------------------------------------------------
class FolderItem(Item, Ext):
  '''
  The FolderItem is an abstract sub-class of a :class:`pysyncml.Item
  <pysyncml.items.base.Item>` which implements the interface as
  defined in OMA DS (aka. SyncML) 1.2.2 for "Folder" (i.e. collection)
  objects and supports the following content-types for the
  :meth:`dump` and :meth:`load` methods:

    * application/vnd.omads-folder

  '''

  #----------------------------------------------------------------------------
  def __init__(self, name=None, parent=None,
               created=None, modified=None, accessed=None,
               role=None,
               hidden=None, system=None, archived=None, delete=None,
               writable=None, readable=None, executable=None,
               *args, **kw):
    '''
    FolderItem constructor which takes the following optional parameters:

    :param name:

      the folder name (relative to the parent folder).

    :param parent:

      the folder\'s containing folder.

    :param created:

      the folder\'s creation time, in number of seconds since
      the epoch.

    :param modified:

      the folder\'s last modification time, in number of seconds
      since the epoch.

    :param accessed:

      the folder\'s last accessed time, in number of seconds
      since the epoch.

    :param role:

      the folder\'s role, primarily used when dealing with collections
      of emails.

    :param hidden:

      the folder\'s "hidden" boolean attribute.

    :param system:

      the folder\'s "system" boolean attribute.

    :param archived:

      the folder\'s "archived" boolean attribute.

    :param delete:

      the folder\'s "delete" boolean attribute.

    :param writable:

      the folder\'s "writable" boolean attribute.

    :param readable:

      the folder\'s "readable" boolean attribute.

    :param executable:

      the folder\'s "executable" boolean attribute.

    '''
    super(FolderItem, self).__init__(*args, **kw)
    self.name        = name
    self.parent      = parent
    self.created     = created
    self.modified    = modified
    self.accessed    = accessed
    self.role        = role
    # attributes
    self.hidden      = hidden
    self.system      = system
    self.archived    = archived
    self.delete      = delete
    self.writable    = writable
    self.readable    = readable
    self.executable  = executable

  #----------------------------------------------------------------------------
  def __cmp__(self, other):
    for attr in ('name', 'parent', 'created', 'modified', 'accessed',
                 'role',
                 'hidden', 'system', 'archived', 'delete',
                 'writable', 'readable', 'executable'):
      ret = cmp(getattr(self, attr), getattr(other, attr))
      if ret != 0:
        return ret
    return 0

  #----------------------------------------------------------------------------
  def dump(self, stream, contentType=None, version=None):
    '''
    Serializes this FolderItem to a byte-stream and writes it to the
    file-like object `stream`. `contentType` and `version` must be one
    of the supported content-types, and if not specified, will default
    to ``application/vnd.omads-folder``.
    '''
    if contentType is None:
      contentType = constants.TYPE_OMADS_FOLDER
    if ctype.getBaseType(contentType) != constants.TYPE_OMADS_FOLDER:
      raise common.InvalidContentType('cannot serialize FolderItem to "%s"' % (contentType,))
    if version is None:
      version = '1.2'
    if version != '1.2':
      raise common.InvalidContentType('invalid folder serialization version "%s"' % (version,))
    root = ET.Element('Folder')
    if self.name is not None:
      ET.SubElement(root, 'name').text = self.name
    for attr in ('created', 'modified', 'accessed'):
      if getattr(self, attr) is None:
        continue
      ET.SubElement(root, attr).text = common.ts_iso(getattr(self, attr))
    if self.role is not None:
      ET.SubElement(root, 'role').text = self.role
    attrs = [attr
             for attr in ('hidden', 'system', 'archived', 'delete', 'writable', 'readable', 'executable')
             if getattr(self, attr) is not None]
    if len(attrs) > 0:
      xa = ET.SubElement(root, 'attributes')
      for attr in attrs:
        ET.SubElement(xa, attr[0]).text = 'true' if getattr(self, attr) else 'false'
    if len(self.extensions) > 0:
      xe = ET.SubElement(root, 'Ext')
      for name, values in self.extensions.items():
        ET.SubElement(xe, 'XNam').text = name
        for value in values:
          ET.SubElement(xe, 'XVal').text = value
    ET.ElementTree(root).write(stream)
    return (constants.TYPE_OMADS_FOLDER + '+xml', '1.2')

  #----------------------------------------------------------------------------
  @classmethod
  def load(cls, stream, contentType=None, version=None):
    '''
    Reverses the effects of the :meth:`dump` method, creating a FileItem
    from the specified file-like `stream` object.
    '''
    if contentType is None:
      contentType = constants.TYPE_OMADS_FOLDER
    if ctype.getBaseType(contentType) == constants.TYPE_OMADS_FILE:
      return FileItem.load(stream, contentType, version)
    if ctype.getBaseType(contentType) != constants.TYPE_OMADS_FOLDER:
      raise common.InvalidContentType('cannot de-serialize FolderItem from "%s"' % (contentType,))
    if version is None:
      version = '1.2'
    if version != '1.2':
      raise common.InvalidContentType('invalid FolderItem de-serialization version "%s"' % (version,))
    ret = FolderItem()
    xdoc = ET.fromstring(stream.read())
    if xdoc.tag != 'Folder':
      raise common.InvalidContent('root of application/vnd.omads-folder XML must be "Folder" not "%s"'
                                  % (xdoc.tag,))
    ret.name = xdoc.findtext('name')
    ret.role = xdoc.findtext('role')
    # todo: do anything with "parent"?...
    # load the date attributes
    for attr in ('created', 'modified', 'accessed'):
      val = xdoc.findtext(attr)
      if val is not None:
        setattr(ret, attr, int(common.parse_ts_iso(val)))
    # load the boolean attributes
    for attr in ('hidden', 'system', 'archived', 'delete',
                 'writable', 'readable', 'executable'):
      val = xdoc.findtext('attributes/' + attr[0])
      if val is not None:
        setattr(ret, attr, val.lower() == 'true')
    return ret

  #----------------------------------------------------------------------------
  @staticmethod
  def fromFilesystem(path):
    if os.path.isfile(path):
      return FileItem.fromFilesystem(path)
    if not os.path.isdir(path):
      raise TypeError('path "%s" is not a file or folder' % (path,))
    stat = os.stat(path)
    ret = FolderItem()
    ret.name       = os.path.basename(path)
    ret.accessed   = stat.st_atime
    ret.modified   = stat.st_mtime
    ret.created    = stat.st_ctime # TODO: this is only correct on windows!...
    # TODO: load folder attributes as well...
    return ret

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
