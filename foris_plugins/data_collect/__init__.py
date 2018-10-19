#
# foris-data_collect-plugin
# Copyright (C) 2018 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
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

import bottle
import os
import time

from datetime import datetime
from urllib.parse import urlencode

from foris import fapi
from foris.common import require_contract_valid
from foris.config import ConfigPageMixin, add_config_page
from foris.config_handlers import BaseConfigHandler
from foris.form import MultiCheckbox, Checkbox, Email
from foris.plugins import ForisPlugin
from foris.state import current_state
from foris.utils import contract_valid, messages
from foris.utils.translators import gettext_dummy as gettext, gettext as _
from foris.utils.routing import reverse


class DataCollectPluginConfigHandler(BaseConfigHandler):

    def get_form(self):
        data = current_state.backend.perform("data_collect", "get_honeypots")

        # convert data from backend to form data
        data["services"] = []
        for minipot in data["minipots"]:
            if data["minipots"][minipot]:
                data["services"].append(minipot)
        del data["minipots"]

        if self.data:
            # Update from post
            if "log_credentials" in self.data:
                data["log_credentials"] = self.data["log_credentials"]

            # services is a multifield which has to be handled differently
            data["services"] = [e for e in self.data.getall("services[]") if e]

        honeypots_form = fapi.ForisForm("honeypots", data)
        fakes = honeypots_form.add_section(
            name="fakes",
            title=_("Emulated services"),
            description=_("One of uCollect's features is emulation of some commonly abused "
                          "services. If this function is enabled, uCollect is listening for "
                          "incoming connection attempts to these services. Enabling of the "
                          "emulated services has no effect if another service is already "
                          "listening on its default port (port numbers are listed below).")
        )

        SERVICES_OPTIONS = (
            ("23tcp", _("Telnet (23/TCP)")),
            ("2323tcp", _("Telnet - alternative port (2323/TCP)")),
            ("80tcp", _("HTTP (80/TCP)")),
            ("3128tcp", _("Squid HTTP proxy (3128/TCP)")),
            ("8123tcp", _("Polipo HTTP proxy (8123/TCP)")),
            ("8080tcp", _("HTTP proxy (8080/TCP)")),
        )

        fakes.add_field(
            MultiCheckbox,
            name="services",
            label=_("Emulated services"),
            args=SERVICES_OPTIONS,
            multifield=True,
        )

        fakes.add_field(
            Checkbox,
            name="log_credentials",
            label=_("Collect credentials"),
            hint=_("If this option is enabled, user names and passwords are collected "
                   "and sent to server in addition to the IP address of the client."),
        )

        def honeypots_form_cb(data):
            msg = {
                "log_credentials": data["log_credentials"],
                "minipots": {k: k in data["services"] for k in dict(SERVICES_OPTIONS)}
            }
            res = current_state.backend.perform("data_collect", "set_honeypots", msg, False)
            res = res if res else {"result": False}  # Set result false when an exception is raised
            return "save_result", res  # store {"result": ...} to be used later...

        honeypots_form.add_callback(honeypots_form_cb)

        return honeypots_form


class CollectionToggleHandler(BaseConfigHandler):
    userfriendly_title = gettext("Data collection")

    def get_form(self):
        data = current_state.backend.perform("data_collect", "get")
        if self.data and "enable" in self.data:
            data["enable"] = self.data["enable"]
        else:
            data["enable"] = data["agreed"]

        form = fapi.ForisForm("enable_collection", data)

        section = form.add_section(
            name="collection_toggle", title=_(self.userfriendly_title),
        )
        section.add_field(
            Checkbox, name="enable", label=_("Enable data collection"),
            preproc=lambda val: bool(int(val))
        )

        def form_cb(data):
            data = current_state.backend.perform(
                "data_collect", "set", {"agreed": data["enable"]})
            return "save_result", data  # store {"result": ...} to be used later...

        form.add_callback(form_cb)

        return form


class RegistrationCheckHandler(BaseConfigHandler):
    """
    Handler for checking of the registration status and assignment to a queried email address.
    """

    userfriendly_title = gettext("Data collection")

    def get_form(self):
        form = fapi.ForisForm("registration_check", self.data)
        main_section = form.add_section(name="check_email", title=_(self.userfriendly_title))
        main_section.add_field(
            Email, name="email", label=_("Email")
        )

        def form_cb(data):
            data = current_state.backend.perform(
                "data_collect", "get_registered",
                {"email": data.get("email"), "language": current_state.language}
            )
            error = None
            registration_number = None
            url = None
            if data["status"] == "unknown":
                error = _("Failed to query the server.")
            elif data["status"] == "not_valid":
                error = _("Failed to verify the router's registration.")
            elif data["status"] in ["free", "foreign"]:
                url = data["url"]
                registration_number = data["registration_number"]

            return "save_result", {
                'success': data["status"] not in ["unknown", "not_valid"],
                'status': data["status"],
                'error': error,
                'url': url,
                'registration_number': registration_number,
            }

        form.add_callback(form_cb)
        return form


class DataCollectPluginPage(ConfigPageMixin, DataCollectPluginConfigHandler):
    userfriendly_title = gettext("Data collection")

    slug = "data_collect"
    menu_order = 80
    template = "data_collect/data_collect"
    template_type = "jinja2"

    SENDING_STATUS_TRANSLATION = {
        'online': gettext("Online"),
        'offline': gettext("Offline"),
        'unknown': gettext("Unknown status"),
    }

    def save(self, *args, **kwargs):
        super().save(no_messages=True, *args, **kwargs)
        result = self.form.callback_results.get('result', False)
        if result:
            messages.success(_("Configuration was successfully saved."))
        else:
            messages.error(_(
                "Failed to update emulated services. Note that you might need to wait till "
                "ucollect is properly installed."
            ))
        return result

    def _prepare_render_args(self, args):
        args['PLUGIN_NAME'] = DataCollectPlugin.PLUGIN_NAME
        args['PLUGIN_STYLES'] = DataCollectPlugin.PLUGIN_STYLES
        args['PLUGIN_STATIC_SCRIPTS'] = DataCollectPlugin.PLUGIN_STATIC_SCRIPTS
        args['PLUGIN_DYNAMIC_SCRIPTS'] = DataCollectPlugin.PLUGIN_DYNAMIC_SCRIPTS

    def render(self, **kwargs):
        self._prepare_render_args(kwargs)

        status = kwargs.pop("status", None)
        if not contract_valid():
            updater_data = current_state.backend.perform("updater", "get_enabled")
            kwargs['updater_disabled'] = not updater_data["enabled"]

            if updater_data["enabled"]:
                collect_data = current_state.backend.perform("data_collect", "get")
                firewall_status = collect_data["firewall_status"]
                firewall_status["seconds_ago"] = int(time.time() - firewall_status["last_check"])
                firewall_status["datetime"] = datetime.fromtimestamp(firewall_status["last_check"])
                firewall_status["state_trans"] = self.SENDING_STATUS_TRANSLATION[
                    firewall_status["state"]]

                ucollect_status = collect_data["ucollect_status"]
                ucollect_status["seconds_ago"] = int(time.time() - ucollect_status["last_check"])
                ucollect_status["datetime"] = datetime.fromtimestamp(ucollect_status["last_check"])
                ucollect_status["state_trans"] = self.SENDING_STATUS_TRANSLATION[
                    ucollect_status["state"]]

                kwargs["ucollect_status"] = ucollect_status
                kwargs["firewall_status"] = firewall_status

                if collect_data["agreed"]:
                    handler = CollectionToggleHandler(bottle.request.POST.decode())
                    kwargs['collection_toggle_form'] = handler.form
                    kwargs['agreed'] = collect_data["agreed"]
                else:
                    email = bottle.request.POST.decode().get(
                        "email", bottle.request.GET.decode().get("email", ""))
                    handler = RegistrationCheckHandler({"email": email})
                    kwargs['registration_check_form'] = handler.form

        return self.default_template(
            form=self.form, title=self.userfriendly_title,
            description=None, status=status,
            **kwargs
        )

    @require_contract_valid(False)
    def _action_check_registration(self):
        handler = RegistrationCheckHandler(bottle.request.POST.decode())
        if not handler.save():
            messages.warning(_("There were some errors in your input."))
            return self.render(registration_check_form=handler.form)

        email = handler.data["email"]

        result = handler.form.callback_results
        kwargs = {}
        if not result["success"]:
            messages.error(_("An error ocurred when checking the registration: "
                             "<br><pre>%(error)s</pre>" % dict(error=result["error"])))
            return self.render()
        else:
            if result["status"] == "owned":
                messages.success(_(
                    "Registration for the entered email is valid. "
                    "Now you can enable the data collection."
                ))
                collection_toggle_handler = CollectionToggleHandler(bottle.request.POST.decode())
                kwargs['collection_toggle_form'] = collection_toggle_handler.form
            elif result["status"] == "foreign":
                messages.warning(
                    _('This router is currently assigned to a different email address. Please '
                      'continue to the <a href="%(url)s">Turris website</a> and use the '
                      'registration code <strong>%(reg_num)s</strong> for a re-assignment to your '
                      'email address.')
                    % dict(url=result["url"], reg_num=result["registration_number"]))
                bottle.redirect(
                    reverse("config_page", page_name="data_collect") + "?" +
                    urlencode({"email": email})
                )
            elif result["status"] == "free":
                messages.info(
                    _('This email address is not registered yet. Please continue to the '
                      '<a href="%(url)s">Turris website</a> and use the registration code '
                      '<strong>%(reg_num)s</strong> to create a new account.')
                    % dict(url=result["url"], reg_num=result["registration_number"]))
                bottle.redirect(
                    reverse("config_page", page_name="data_collect") + "?" +
                    urlencode({"email": email})
                )
            elif result["status"] == "not_found":
                messages.error(
                    _('Router failed to authorize. Please try to validate our email later.'))
                bottle.redirect(
                    reverse("config_page", page_name="data_collect") + "?" +
                    urlencode({"email": email})
                )
        return self.render(
            status=result["status"],
            registration_url=result["url"],
            reg_num=result["registration_number"],
            **kwargs
        )

    @require_contract_valid(False)
    def _action_toggle_collecting(self):
        if bottle.request.method != 'POST':
            messages.error(_("Wrong HTTP method."))
            bottle.redirect(reverse("config_page", page_name="data_collect"))

        handler = CollectionToggleHandler(bottle.request.POST.decode())
        if handler.save():
            messages.success(_("Configuration was successfully saved."))
            bottle.redirect(reverse("config_page", page_name="data_collect"))

        messages.warning(_("There were some errors in your input."))
        return super().render(collection_toggle_form=handler.form)

    def call_action(self, action):
        if action == "check_registration":
            return self._action_check_registration()
        elif action == "toggle_collecting":
            return self._action_toggle_collecting()
        raise bottle.HTTPError(404, "Unknown action")


# plugin definition
class DataCollectPlugin(ForisPlugin):
    PLUGIN_NAME = "data_collect"
    DIRNAME = os.path.dirname(os.path.abspath(__file__))

    PLUGIN_STYLES = [
        "css/data_collect.css",
    ]
    PLUGIN_STATIC_SCRIPTS = [
    ]
    PLUGIN_DYNAMIC_SCRIPTS = [
    ]

    def __init__(self, app):
        super().__init__(app)
        add_config_page(DataCollectPluginPage)
