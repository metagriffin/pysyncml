# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/05/15
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
The ``pysyncml.model.devinfo`` provides the device information sharing
classes.
'''

import sys, logging, inspect
import xml.etree.ElementTree as ET
from sqlalchemy import Column, Integer, Boolean, String, Text, ForeignKey
from sqlalchemy.orm import relation, synonym, backref
from sqlalchemy.orm.exc import NoResultFound
from .. import constants, common

log = logging.getLogger(__name__)

# TODO: DeviceInfo should implement something like items.base.Ext

#------------------------------------------------------------------------------
def notNoneOr(value, other):
  return value if value is not None else other

#------------------------------------------------------------------------------
def decorateModel(model):

  #----------------------------------------------------------------------------
  class DeviceInfo(model.DatabaseObject):
    # todo: since adapter <=> device is one-to-one, shouldn't this be a primary key?...
    adapter_id        = Column(Integer, ForeignKey('%s_adapter.id' % (model.prefix,),
                                                   onupdate='CASCADE', ondelete='CASCADE'),
                               nullable=False, index=True)
    adapter           = relation('Adapter', backref=backref('_devinfo', uselist=False,
                                                            cascade='all, delete-orphan',
                                                            passive_deletes=True))
    devID             = Column(String(4095), nullable=False)
    devType           = Column(String(4095), nullable=False, default=constants.DEVTYPE_WORKSTATION)
    manufacturerName  = Column(String(4095), nullable=True, default='-')
    modelName         = Column(String(4095), nullable=True, default='-')
    oem               = Column(String(4095), nullable=True, default='-')
    hardwareVersion   = Column(String(255), nullable=True, default='-')
    firmwareVersion   = Column(String(255), nullable=True, default='-')
    softwareVersion   = Column(String(255), nullable=True, default='-')
    utc               = Column(Boolean, nullable=True, default=True)
    largeObjects      = Column(Boolean, nullable=True, default=True)
    hierarchicalSync  = Column(Boolean, nullable=True, default=True)
    numberOfChanges   = Column(Boolean, nullable=True, default=True)

    strAttributeMap = [
      ('manufacturerName',    'Man'),
      ('modelName',           'Mod'),
      ('oem',                 'OEM'),
      ('firmwareVersion',     'FwV'),
      ('softwareVersion',     'SwV'),
      ('hardwareVersion',     'HwV'),
      ('devID',               'DevID'),
      ('devType',             'DevTyp'),
      ]

    boolAttributeMap = [
      ('utc',                 'UTC'),
      ('largeObjects',        'SupportLargeObjs'),
      ('hierarchicalSync',    'SupportHierarchicalSync'),
      ('numberOfChanges',     'SupportNumberOfChanges'),
      ]

    #--------------------------------------------------------------------------
    def __init__(self, *args, **kw):
      # TODO: why on *EARTH* do i have to do this?...
      self._setDefaults()
      super(DeviceInfo, self).__init__(*args, **kw)

    #----------------------------------------------------------------------------
    def __repr__(self):
      ret = '<Device "%s": devType=%s' % (self.devID, self.devType)
      for attr in self.__table__.c.keys():
        if attr in self.__syscols__ \
           or attr in ('devID', 'devType', 'adapter_id',) \
           or getattr(self, attr) is None:
          continue
        ret += '; %s=%s' % (attr, str(getattr(self, attr)))
      return ret + '>'

    # #----------------------------------------------------------------------------
    # def save(self, adapter):
    #   if adapter._db.device is None:
    #     adapter._db.device = adapter.model.Device()
    #   self._db = adapter._db.device
    #   for attr in common.dbattrs(adapter.model.Device, DeviceInfo):
    #     setattr(self._db, attr, getattr(self, attr))

    # #----------------------------------------------------------------------------
    # @staticmethod
    # def load(adapter):
    #   if adapter._db.device is None:
    #     return None
    #   ret = DeviceInfo()
    #   ret._db = adapter._db.device
    #   for attr in common.dbattrs(adapter.model.Device, DeviceInfo):
    #     setattr(ret, attr, getattr(ret._db, attr))
    #   return ret

    #----------------------------------------------------------------------------
    def toSyncML(self, dtdVersion, stores):
      if dtdVersion is None:
        dtdVersion = constants.SYNCML_DTD_VERSION_1_2
      if dtdVersion != constants.SYNCML_DTD_VERSION_1_2:
        raise common.InternalError('unsupported DTD version "%s"' % (dtdVersion,))
      xret = ET.Element('DevInf', {'xmlns': constants.NAMESPACE_DEVINF})
      ET.SubElement(xret, 'VerDTD').text = dtdVersion
      for attr, xname in DeviceInfo.strAttributeMap:
        # todo: should i enforce the fact that these are all *required*?...
        if getattr(self, attr) is not None:
          ET.SubElement(xret, xname).text = getattr(self, attr)
      for attr, xname in DeviceInfo.boolAttributeMap:
        if getattr(self, attr) is not None and getattr(self, attr):
          ET.SubElement(xret, xname)
      for store in stores or []:
        xret.append(store.toSyncML())
      return xret

    #----------------------------------------------------------------------------
    @staticmethod
    def fromSyncML(xnode):
      # todo: it would be *great* if i could delete the namespacing here...
      devinfo   = DeviceInfo()
      stores    = []
      dtdVersion = xnode.findtext('VerDTD')
      if dtdVersion != constants.SYNCML_DTD_VERSION_1_2:
        raise common.ProtocolError('unsupported DTD version "%s"' % (dtdVersion,))
      for attr, xname in DeviceInfo.strAttributeMap:
        setattr(devinfo, attr, xnode.findtext(xname))
      for attr, xname in DeviceInfo.boolAttributeMap:
        setattr(devinfo, attr, xnode.find(xname) is not None)
      for child in xnode:
        if child.tag != 'DataStore':
          continue
        stores.append(model.Store.fromSyncML(child))
      return (devinfo, stores)

  model.DeviceInfo = DeviceInfo

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
