# Copyright 2017-2018 Capital One Services, LLC
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

try:
    from botocore.config import Config
except ImportError:
    from c7n.config import Bag as Config  # pragma: no cover

from .core import EventAction
from c7n import utils
from c7n.manager import resources
from c7n.version import version as VERSION


class LambdaInvoke(EventAction):
    """Invoke an arbitrary lambda

    serialized invocation parameters

     - resources / collection of resources
     - policy / policy that is invoke the lambda
     - action / action that is invoking the lambda
     - event / cloud trail event if any
     - version / version of custodian invoking the lambda

    We automatically batch into sets of 250 for invocation,
    We try to utilize async invocation by default, this imposes
    some greater size limits of 128kb which means we batch
    invoke.

    Example::

     - type: invoke-lambda
       function: my-function

    Note if your synchronously invoking the lambda, you may also need
    to configure the timeout, to avoid multiple invokes. The default
    is 90s, if the lambda doesn't respond within that time the boto
    sdk will invoke the lambda again with the same
    arguments. Alternatively use async: true

    """
    schema_alias = True
    schema = {
        'type': 'object',
        'required': ['type', 'function'],
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['invoke-lambda']},
            'function': {'type': 'string'},
            'region': {'type': 'string'},
            'async': {'type': 'boolean'},
            'qualifier': {'type': 'string'},
            'batch_size': {'type': 'integer'},
            'timeout': {'type': 'integer'},
            'vars': {'type': 'object'},
        }
    }

    permissions = ('lambda:InvokeFunction',
               'iam:ListAccountAliases',)

    def process(self, resources, event=None):
        params = dict(FunctionName=self.data['function'])
        if self.data.get('qualifier'):
            params['Qualifier'] = self.data['Qualifier']

        if self.data.get('async', True):
            params['InvocationType'] = 'Event'

        config = Config(read_timeout=self.data.get(
            'timeout', 90), region_name=self.data.get('region', None))
        client = utils.local_session(
            self.manager.session_factory).client('lambda', config=config)
        alias = utils.get_account_alias_from_sts(
            utils.local_session(self.manager.session_factory))

        payload = {
            'version': VERSION,
            'event': event,
            'account_id': self.manager.config.account_id,
            'account': alias,
            'region': self.manager.config.region,
            'action': self.data,
            'policy': self.manager.data}

        results = []
        for resource_set in utils.chunks(resources, self.data.get('batch_size', 250)):
            payload['resources'] = resource_set
            params['Payload'] = utils.dumps(payload)
            result = client.invoke(**params)
            result['Payload'] = result['Payload'].read()
            if isinstance(result['Payload'], bytes):
                result['Payload'] = result['Payload'].decode('utf-8')
            results.append(result)
        return results

    @classmethod
    def register_resources(klass, registry, resource_class):
        if 'invoke-lambda' not in resource_class.action_registry:
            resource_class.action_registry.register('invoke-lambda', LambdaInvoke)


resources.subscribe(LambdaInvoke.register_resources)
