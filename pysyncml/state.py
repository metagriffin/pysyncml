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
The ``pysyncml.state`` is an internal package that abstracts SyncML
state related objects, including :class:`pysyncml.state.Session`,
:class:`pysyncml.state.Request` and
:class:`pysyncml.state.Command`.
'''

from .common import adict

#------------------------------------------------------------------------------
class Session(adict):
  '''
  Stores session state information for managing SyncML transactions.

  .. important::

    *IMPORTANT*: anything stored in this object MUST be serializable as it
    may be serialized by servers after closing a client connection!

  '''
  def __init__(self, *args, **kw):
    # note: overriding dict's init to set some default values
    self.id        = 1
    self.isServer  = True
    self.msgID     = 1
    self.cmdID     = 0
    self.dsstates  = dict()
    self.stats     = dict()
    super(Session, self).__init__(*args, **kw)
  @property
  def nextMsgID(self):
    # TODO: what if the session is in server mode... then the msgID is
    #       controlled by the client, right? and it may not be an int...
    self.msgID += 1
    self.cmdID = 0
    return self.msgID
  @property
  def nextCmdID(self):
    self.cmdID += 1
    return self.cmdID

#------------------------------------------------------------------------------
class Request(adict): pass
class Response(adict): pass

#------------------------------------------------------------------------------
class Command(adict):
  nonStringAttributes = ('data',)
  def __init__(self, **kw):
    # note: explicitly overriding dict's init behavior because Command does
    #       something special with attribute values (conditionally turns them
    #       into strings)
    for k, v in kw.items():
      setattr(self, k, v)
  def __setattr__(self, key, value):
    if value is None or key in Command.nonStringAttributes or key.startswith('_'):
      self[key] = value
    else:
      self[key] = str(value)
    return self

#------------------------------------------------------------------------------
class Stats(adict):
  def __init__(self, *args, **kw):
    # note: overriding dict's init to set some default values
    self.mode      = None
    self.hereAdd   = 0
    self.hereMod   = 0
    self.hereDel   = 0
    self.hereErr   = 0
    self.peerAdd   = 0
    self.peerMod   = 0
    self.peerDel   = 0
    self.peerErr   = 0
    self.conflicts = 0
    self.merged    = 0
    super(Stats, self).__init__(*args, **kw)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
