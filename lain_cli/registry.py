from json.decoder import JSONDecodeError

import requests
from tenacity import retry, stop_after_attempt, wait_fixed

from lain_cli.utils import (
    RegistryUtils,
    RequestClientMixin,
    subprocess_run,
    tell_cluster_config,
)


class Registry(RequestClientMixin, RegistryUtils):
    headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}

    def __init__(self, registry=None, **kwargs):
        if not registry:
            cc = tell_cluster_config()
            registry = cc['registry']

        self.registry = registry
        if '/' in registry:
            host, self.namespace = registry.split('/')
        else:
            host = registry
            self.namespace = ''

        if host == 'docker.io':
            api_host = 'index.docker.io'
            self.endpoint = f'http://{api_host}'
        else:
            https = kwargs.get('registry_endpoint_use_https', False)
            protocol = 'https' if https else 'http'
            self.endpoint = f'{protocol}://{registry}'

        self.dockerhub_password = kwargs.get('dockerhub_password')
        self.dockerhub_username = kwargs.get('dockerhub_username')

        self.token_fetch_cmd = kwargs.get('registry_token_fetch_cmd')
        self.token_type = kwargs.get('registry_token_type', 'Bearer')

    def prepare_token(self, scope):
        if self.token_fetch_cmd:
            res = subprocess_run(
                self.token_fetch_cmd,
                shell=True,
                check=True,
                capture_output=True,
            )
            token = res.stdout.decode().strip()

        elif all([self.dockerhub_password, self.dockerhub_username]):
            res = requests.post(
                'https://auth.docker.io/token',
                data={
                    'grant_type': 'password',
                    'service': 'registry.docker.io',
                    'scope': scope,
                    'client_id': 'dockerengine',
                    'username': self.dockerhub_username,
                    'password': self.dockerhub_password,
                },
            )
            token = res.json()['access_token']

        else:
            token = None

        if token:
            self.headers['Authorization'] = f'{self.token_type} {token}'

    def request(self, *args, **kwargs):
        res = super().request(*args, **kwargs)
        try:
            responson = res.json()
        except JSONDecodeError as e:
            raise ValueError(f'bad registry response: {res.text}') from e
        if not isinstance(responson, dict):
            return res
        errors = responson.get('errors')
        if errors:
            raise ValueError(f'registry error: headers {res.headers}, errors {errors}')
        return res

    def list_repos(self):
        path = '/v2/_catalog'
        responson = self.get(path, params={'n': 9999}, timeout=90).json()
        return responson.get('repositories', [])

    @retry(reraise=True, wait=wait_fixed(2), stop=stop_after_attempt(6))
    def delete_image(self, repo, tag=None):
        path = f'/v2/{repo}/manifests/{tag}'
        headers = self.head(path).headers
        docker_content_digest = headers.get('Docker-Content-Digest')
        if not docker_content_digest:
            return
        path = f'/v2/{repo}/manifests/{docker_content_digest}'
        return self.delete(path, timeout=20)  # 不知道为啥删除操作就是很慢, 只好在这里单独放宽

    def list_tags(self, repo_name, n=None, timeout=90):
        repo = f'{self.namespace}/{repo_name}' if self.namespace else repo_name
        path = f'/v2/{repo}/tags/list'
        self.prepare_token(scope=f'repository:{repo}:pull,push')
        responson = self.get(path, params={'n': 1000}, timeout=timeout).json()
        if 'tags' not in responson:
            return []
        tags = self.sort_and_filter(responson.get('tags') or [], n=n)
        return tags
