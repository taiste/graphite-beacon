import json
import requests

from tornado import httpclient as hc
from tornado import gen

from graphite_beacon.handlers import LOGGER, AbstractHandler
from graphite_beacon.template import TEMPLATES


class SlackHandler(AbstractHandler):

    name = 'slack'

    # Default options
    defaults = {
        'webhook': None,
        'channel': None,
        'username': 'graphite-beacon',
    }

    emoji = {
        'critical': ':exclamation:',
        'warning': ':warning:',
        'normal': ':white_check_mark:',
    }

    def init_handler(self):
        self.webhook = self.options.get('webhook')
        assert self.webhook, 'Slack webhook is not defined.'

        self.channel = self.options.get('channel')
        if self.channel and not self.channel.startswith(('#', '@')):
            self.channel = '#' + self.channel
        self.username = self.options.get('username')
        self.client = hc.AsyncHTTPClient()

    def get_message(self, level, criticality, alert, value, target=None, ntype=None, rule=None):  # pylint: disable=unused-argument
        msg_type = 'slack' if ntype == 'graphite' else 'short'
        tmpl = TEMPLATES[ntype][msg_type]
        return tmpl.generate(
            level=level, reactor=self.reactor, alert=alert, value=value, target=target, criticality=criticality).strip()


    def get_alert_criticality(self, level, alert, value, target=None, ntype=None, rule=None):
        try:
            criticality = -1
            username = str(self.reactor.options.get('auth_username'))
            password = str(self.reactor.options.get('auth_password'))
            try:
                id_org, metric = target.split(".")
            except Exception:
                return -1

            if metric == "message_in":            
                activity_data = requests.get("https://"+username+":"+password+"@stats.valopilkkupalvelu.fi/render/?target=summarize(stats.counters.suti."+id_org+".keep_alive_ok.count%2C'100min','sum',true)&from=-100min&format=json").json()
               
                if len(activity_data) == 0 or activity_data[0]['datapoints'][-1][0] == None:
                    return -2
            try:
                criticality_data = requests.get("https://"+username+":"+password+"@stats.valopilkkupalvelu.fi/render/?target=summarize(stats.counters.valopilkku.orders.VP."+id_org+"*.request.count%2C'60min','sum',true)&from=-60min&format=json").json()
            except Exception:
                return -1

            if len(criticality_data) > 0:
                criticality = criticality_data[0]['datapoints'][-1][0]

            return criticality
        except Exception:
            return -1

    @gen.coroutine
    def notify(self, level, *args, **kwargs):
        LOGGER.debug("Handler (%s) %s", self.name, level)
        criticality = self.get_alert_criticality(level, *args, **kwargs)       
        if criticality > -2:
            message = self.get_message(level, criticality,  *args, **kwargs)
            data = dict()
            data['username'] = self.username
            data['text'] = message
            data['icon_emoji'] = self.emoji.get(level, ':warning:')
            if self.channel:
                data['channel'] = self.channel
            body = json.dumps(data)
            yield self.client.fetch(
                self.webhook,
                method='POST',
                headers={'Content-Type': 'application/json'},
                body=body
            )
