#
# foris-data_collect-plugin
# Copyright (C) 2019 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
#

import typing

from foris.utils.translators import gettext as _
from foris.state import current_state


def updater_always_on() -> typing.Optional[str]:
    """ Determines whether updater is not supposed to be disabled
    :returns: None if updater can be disable, reason why not otherwise
    """

    if current_state.backend.perform("data_collect", "get")["agreed"]:
        return _(
            "Data collection is currently enabled. "
            "You can not disable updater without disabling the data collection first."
        )
