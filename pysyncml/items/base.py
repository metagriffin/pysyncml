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
The ``pysyncml.items.base`` module defines the abstract interface
:class:`pysyncml.Item <pysyncml.items.base.Item>`, the base class for
all pysyncml synchronized objects.
'''

import StringIO
from .. import constants

#------------------------------------------------------------------------------
class Item(object):
  '''
  An ``Item`` declares the abstract interface of objects that are
  synchronized by the pysyncml framework. The only required attributes
  are the :attr:`id` property, and the :meth:`dump` and :meth:`load`
  methods. Note that the latter two are currently never invoked
  directly, and are called via the :class:`pysyncml.Agent
  <pysyncml.agents.base.Agent>` interface. They are therefore not
  technically required, but are highly recommended for
  forward-compatibility.
  '''

  #: The local datastore-unique identifier for this object. Although
  #: the exact datatype is undefined, it must be convertible to a
  #: string via a call to ``str(item.id)``.
  id = None

  #----------------------------------------------------------------------------
  def __init__(self, id=None, *args, **kw):
    super(Item, self).__init__(*args, **kw)
    self.id = id

  #----------------------------------------------------------------------------
  def dump(self, stream, contentType=None, version=None):
    '''
    Converts this Item to serialized form (such that it can be
    transported over the wire) and writes it to the provided file-like
    `stream` object. For agents that support multiple content-types,
    the desired `contentType` and `version` will be specified as a
    parameter. If `contentType` and `version` are None, appropriate
    default values should be used. For agents that concurrently use
    multiple content-types, the return value may be a two-element
    tuple of (contentType, version), thus overriding or enhancing the
    provided values.
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  def dumps(self, contentType=None, version=None):
    '''
    [OPTIONAL] Identical to :meth:`dump`, except the serialized form
    is returned as a string representation. As documented in
    :meth:`dump`, the return value can optionally be a three-element
    tuple of (contentType, version, data) if the provided content-type
    should be overridden or enhanced. The default implementation just
    wraps :meth:`dump`.
    '''
    buf = StringIO.StringIO()
    ret = self.dump(buf, contentType, version)
    if ret is None:
      return buf.getvalue()
    return (ret[0], ret[1], buf.getvalue())

  #----------------------------------------------------------------------------
  @classmethod
  def load(cls, stream, contentType=None, version=None):
    '''
    Reverses the effects of the :meth:`dump` method, and returns the
    de-serialized Item from the file-like source `stream`.

    Note: `version` will typically be ``None``, so it should either be
    auto-determined, or not used. This is an issue in the SyncML
    protocol, and is only here for symmetry with :meth:`dump` and as
    "future-proofing".
    '''
    raise NotImplementedError()

  #----------------------------------------------------------------------------
  @classmethod
  def loads(cls, data, contentType=None, version=None):
    '''
    [OPTIONAL] Identical to :meth:`load`, except the serialized form
    is provided as a string representation in `data` instead of as a
    stream. The default implementation just wraps :meth:`load`.
    '''
    buf = StringIO.StringIO(data)
    return cls.load(buf, contentType, version)

  #----------------------------------------------------------------------------
  def __repr__(self):
    ret = '<%s.%s' % (self.__class__.__module__, self.__class__.__name__)
    for key, val in self.__dict__.items():
      if val is None:
        continue
      val = repr(val)
      if len(val) > 40:
        val = val[:40] + '...'
      ret += ' %s=%s' % (key, val)
    return ret + '>'

#------------------------------------------------------------------------------
class Ext(object):

  #----------------------------------------------------------------------------
  def __init__(self, *args, **kw):
    super(Ext, self).__init__(*args, **kw)
    # extensions - dict: keys => ( list ( values ) )
    self.extensions  = dict()

  #----------------------------------------------------------------------------
  def addExtension(self, name, value):
    if name not in self.extensions:
      self.extensions[name] = []
    self.extensions[name].append(value)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
