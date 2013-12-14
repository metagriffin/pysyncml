# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/06/23
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
The ``pysyncml.ctype`` module exposes the
:class:`pysyncml.ContentTypeInfo <pysyncml.ctype.ContentTypeInfo>`
class, which abstracts content-type handling with respect to
transmission, reception and preferred status within SyncML handling.
'''

import xml.etree.ElementTree as ET
from .common import adict

__all__ = 'ContentTypeInfo',

#------------------------------------------------------------------------------
def getBaseType(contentType):
  if '+' not in contentType:
    return contentType
  return contentType.split('+', 1)[0]

#------------------------------------------------------------------------------
class ContentTypeInfoMixIn:

  #----------------------------------------------------------------------------
  def merge(self, other):
    if self.ctype != other.ctype \
       or self.versions != other.versions \
       or self.preferred != self.preferred:
      return False
    self.transmit = self.transmit or other.transmit
    self.receive = self.receive or other.receive
    return True

  #----------------------------------------------------------------------------
  def __str__(self):
    ret = '%s@%s:' % (self.ctype, ','.join(self.versions))
    if self.preferred:
      ret += 'Pref'
    if self.transmit:
      ret += 'Tx'
    if self.receive:
      ret += 'Rx'
    return ret

  #----------------------------------------------------------------------------
  def __repr__(self):
    return self.__str__()

  #----------------------------------------------------------------------------
  def describe(self, s1):
    s1.write(self.ctype)
    s1.write(' versions ' if len(self.versions) != 1 else ' version ')
    s1.write(', '.join(self.versions))
    flags = []
    if self.preferred:
      flags.append('preferred')
    if self.transmit:
      flags.append('tx')
    if self.receive:
      flags.append('rx')
    if len(flags) > 0:
      s1.write(' (')
      s1.write(', '.join(flags))
      s1.write(')')
    s1.write('\n')

  #----------------------------------------------------------------------------
  def toSyncML(self, nodeName=None, uniqueVerCt=False):
    '''
    Returns an ElementTree node representing this ContentTypeInfo. If
    `nodeName` is not None, then it will be used as the containing
    element node name (this is useful, for example, to differentiate
    between a standard content-type and a preferred content-type). If
    `uniqueVerCt` is True, then an array of elements will be returned
    instead of a single element with multiple VerCT elements (for
    content-types that support multiple versions).
    '''
    if uniqueVerCt:
      ret = []
      for v in self.versions:
        tmp = ET.Element(nodeName or 'ContentType')
        ET.SubElement(tmp, 'CTType').text = self.ctype
        ET.SubElement(tmp, 'VerCT').text = v
        ret.append(tmp)
      return ret
    ret = ET.Element(nodeName or 'ContentType')
    ET.SubElement(ret, 'CTType').text = self.ctype
    for v in self.versions:
      ET.SubElement(ret, 'VerCT').text = v
    return ret

  #----------------------------------------------------------------------------
  @classmethod
  def fromSyncML(klass, xnode):
    return klass(
      ctype     = xnode.findtext('CTType'),
      versions  = [x.text for x in xnode.findall('VerCT')],
      preferred = xnode.tag.endswith('-Pref'),
      transmit  = 'Tx' in xnode.tag,
      receive   = 'Rx' in xnode.tag,
      )

#------------------------------------------------------------------------------
class ContentTypeInfo(adict, ContentTypeInfoMixIn):
  '''
  The ContentTypeInfo class defines a content-type handling capability of
  a pysyncml Agent.
  '''

  #----------------------------------------------------------------------------
  def __init__(self, ctype=None, versions=None,
               preferred=False, transmit=True, receive=True,
               *args, **kw):
    '''
    The ContentTypeInfo constructor supports the following parameters:

    :param ctype:

      specifies the content-type string, for example ``\'text/plain\'``.

    :param versions:

      a version string (or list thereof) of the specified `ctype` that
      are supported, for example ``[\'1.0\', \'1.1\']``.

    :param preferred:

      boolean specifying whether or not this is the preferred
      content-type. Note that only one ContentTypeInfo can be marked
      as being preferred.

    :param transmit:

      boolean specifying whether or not the Agent can `transmit` this
      content-type, i.e. a call to :meth:`pysyncml.Agent.dumpItem
      <pysyncml.agents.base.Agent.dumpItem>` with this content-type
      will succeed.

    :param receive:

      boolean specifying whether or not the Agent can `receive` this
      content-type, i.e. a call to :meth:`pysyncml.Agent.loadItem
      <pysyncml.agents.base.Agent.loadItem>` with this content-type
      will succeed.

    '''
    super(ContentTypeInfo, self).__init__(*args, **kw)
    self.ctype     = ctype
    if isinstance(versions, basestring):
      versions = [versions]
    self.versions  = versions
    self.preferred = preferred
    self.transmit  = transmit
    self.receive   = receive

  def __str__(self):
    return ContentTypeInfoMixIn.__str__(self)

  def __repr__(self):
    return ContentTypeInfoMixIn.__repr__(self)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
