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
The ``pysyncml.items.file`` module defines the abstract interface to an
OMA DS File object via the :class:`pysyncml.items.file.FileItem` class.
'''

import os
import xml.etree.ElementTree as ET
from .base import Item, Ext
from .. import constants, common, ctype

#------------------------------------------------------------------------------
class FileItem(Item, Ext):
  '''
  The FileItem is an abstract sub-class of a :class:`pysyncml.Item
  <pysyncml.items.base.Item>` which implements the interface as defined
  in OMA DS (aka. SyncML) 1.2.2 for "File" objects and supports the
  following content-types for the :meth:`dump` and :meth:`load` methods:

    * application/vnd.omads-file

  '''

  #----------------------------------------------------------------------------
  def __init__(self, name=None, parent=None,
               created=None, modified=None, accessed=None,
               contentType=None, body=None, size=None,
               hidden=None, system=None, archived=None, delete=None,
               writable=None, readable=None, executable=None,
               *args, **kw):
    '''
    FileItem constructor which takes the following optional parameters:

    :param name:

      the file name (relative to the parent folder).

    :param parent:

      the file\'s containing folder.

    :param created:

      the file\'s creation time, in number of seconds since
      the epoch.

    :param modified:

      the file\'s last modification time, in number of seconds
      since the epoch.

    :param accessed:

      the file\'s last accessed time, in number of seconds
      since the epoch.

    :param contentType:

      the file\'s content-type.

    :param body:

      the file\'s content.

    :param size:

      the size of file\'s content, specified as an integer. If not
      specified and `body` is specified, the size will be taken from
      the `body` parameter.

    :param hidden:

      the file\'s "hidden" boolean attribute.

    :param system:

      the file\'s "system" boolean attribute.

    :param archived:

      the file\'s "archived" boolean attribute.

    :param delete:

      the file\'s "delete" boolean attribute.

    :param writable:

      the file\'s "writable" boolean attribute.

    :param readable:

      the file\'s "readable" boolean attribute.

    :param executable:

      the file\'s "executable" boolean attribute.

    '''
    super(FileItem, self).__init__(*args, **kw)
    self.name        = name
    self.parent      = parent
    self.created     = created
    self.modified    = modified
    self.accessed    = accessed
    self.contentType = contentType
    self.body        = body
    self.size        = size
    if self.size is None and self.body is not None:
      self.size      = len(body)
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
                 'contentType', 'body', 'size',
                 'hidden', 'system', 'archived', 'delete',
                 'writable', 'readable', 'executable'):
      ret = cmp(getattr(self, attr), getattr(other, attr))
      if ret != 0:
        return ret
    return 0

  #----------------------------------------------------------------------------
  def dump(self, stream, contentType=None, version=None):
    '''
    Serializes this FileItem to a byte-stream and writes it to the
    file-like object `stream`. `contentType` and `version` must be one
    of the supported content-types, and if not specified, will default
    to ``application/vnd.omads-file``.
    '''
    if contentType is None:
      contentType = constants.TYPE_OMADS_FILE
    if ctype.getBaseType(contentType) != constants.TYPE_OMADS_FILE:
      raise common.InvalidContentType('cannot serialize FileItem to "%s"' % (contentType,))
    if version is None:
      version = '1.2'
    if version != '1.2':
      raise common.InvalidContentType('invalid file serialization version "%s"' % (version,))
    root = ET.Element('File')
    if self.name is not None:
      ET.SubElement(root, 'name').text = self.name
    # todo: do anything with "parent"?...
    for attr in ('created', 'modified', 'accessed'):
      if getattr(self, attr) is None:
        continue
      ET.SubElement(root, attr).text = common.ts_iso(getattr(self, attr))
    if self.contentType is not None:
      ET.SubElement(root, 'cttype').text = self.contentType
    attrs = [attr
             for attr in ('hidden', 'system', 'archived', 'delete', 'writable', 'readable', 'executable')
             if getattr(self, attr) is not None]
    if len(attrs) > 0:
      xa = ET.SubElement(root, 'attributes')
      for attr in attrs:
        ET.SubElement(xa, attr[0]).text = 'true' if getattr(self, attr) else 'false'
    if self.body is not None:
      ET.SubElement(root, 'body').text = self.body
    if self.body is None and self.size is not None:
      ET.SubElement(root, 'size').text = str(self.size)
    if len(self.extensions) > 0:
      xe = ET.SubElement(root, 'Ext')
      for name, values in self.extensions.items():
        ET.SubElement(xe, 'XNam').text = name
        for value in values:
          ET.SubElement(xe, 'XVal').text = value
    ET.ElementTree(root).write(stream)
    return (constants.TYPE_OMADS_FILE + '+xml', '1.2')

  #----------------------------------------------------------------------------
  @classmethod
  def load(cls, stream, contentType=None, version=None):
    '''
    Reverses the effects of the :meth:`dump` method, creating a FileItem
    from the specified file-like `stream` object.
    '''
    if contentType is None:
      contentType = constants.TYPE_OMADS_FILE
    if ctype.getBaseType(contentType) == constants.TYPE_OMADS_FOLDER:
      from .folder import FolderItem
      return FolderItem.load(stream, contentType, version)
    if ctype.getBaseType(contentType) != constants.TYPE_OMADS_FILE:
      raise common.InvalidContentType('cannot de-serialize FileItem from "%s"' % (contentType,))
    if version is None:
      version = '1.2'
    if version != '1.2':
      raise common.InvalidContentType('invalid FileItem de-serialization version "%s"' % (version,))
    ret = FileItem()
    data = stream.read()
    xdoc = ET.fromstring(data)
    if xdoc.tag != 'File':
      raise common.InvalidContent('root of application/vnd.omads-file XML must be "File" not "%s"'
                                  % (xdoc.tag,))
    ret.name = xdoc.findtext('name')
    ret.body = xdoc.findtext('body')
    ret.size = xdoc.findtext('size')
    if ret.body is not None:
      ret.size = len(ret.body)
    elif ret.size is not None:
      ret.size = int(ret.size)
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
    if os.path.isdir(path):
      from .folder import FolderItem
      return FolderItem.fromFilesystem(path)
    if not os.path.isfile(path):
      raise TypeError('path "%s" is not a file or folder' % (path,))
    stat = os.stat(path)
    ret = FileItem()
    ret.name       = os.path.basename(path)
    ret.accessed   = stat.st_atime
    ret.modified   = stat.st_mtime
    ret.created    = stat.st_ctime # TODO: this is only correct on windows!...
    # TODO: load folder attributes as well...
    return ret

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
