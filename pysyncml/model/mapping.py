# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/06/24
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
The ``pysyncml.model.mapping`` provides the model for mapping
client-side object IDs (LUIDs) to server-side object IDs (GUIDs),
stored only on the server-side.
'''

import sys, logging, inspect
import xml.etree.ElementTree as ET
from sqlalchemy import Column, Integer, Boolean, String, Text, ForeignKey
from sqlalchemy.orm import relation, synonym, backref
from sqlalchemy.orm.exc import NoResultFound
from .. import constants, common

log = logging.getLogger(__name__)

#------------------------------------------------------------------------------
def decorateModel(model):

  #----------------------------------------------------------------------------
  class Mapping(model.DatabaseObject):
    store_id          = Column(Integer, ForeignKey('%s_store.id' % (model.prefix,),
                                                   onupdate='CASCADE', ondelete='CASCADE'),
                               nullable=False, index=True)
    # store             = relation('Store', backref=backref('mappings',
    #                                                       cascade='all, delete-orphan',
    #                                                       passive_deletes=True))
    guid              = Column(String(4095), index=True, nullable=True)
    luid              = Column(String(4095), index=True, nullable=True)

  model.Mapping = Mapping

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
