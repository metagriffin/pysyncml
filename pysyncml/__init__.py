# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/04/20
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
The ``pysyncml`` package provides a pure-python implementation of the
SyncML adapter framework and protocol. It does not actually provide
any storage or agent implementations - these must be provided by the
calling program.
'''

from .constants import *
from .common import *
from .agents import *
from .items import *
from .context import *
from .codec import *
from .state import *
from .ctype import *
from .model import enableSqliteCascadingDeletes
from .change import *

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
