## lain

### Installation

1. 参考[文档](https://github.com/nftxyz/gl-infra#connect-to-vpc-with-vpn)连接 grandline VPN

2. 安装 lain

```sh
pip install lain -i https://pypi.0xgl.xyz
```

如果提示输入用户名密码，请在 1pwd 搜索 `pypi.0xgl.xyz`

3. 参考[集群配置文档](lain_cli/cluster_values/grandline.md)所属安装依赖和进行配置

4. 参考下面的 Upstream README ，使用 lain 。集群名为 `grandline` 或 `test` ，例如

```sh
lain use grandline
```

### Domains

|            | grandline 集群（生产环境）              | test 集群（测试环境） |
| ---------- | --------------------------------------- | --------------------- |
| 外网可访问 | `0xnftsee.xyz`, `uninvitedelephant.xyz` | `gl-test.xyz`         |
| 仅内网访问 | `0xgl.xyz`                              | `test.0xgl.xyz`       |

只支持一级子域名，如 `ue.gl-test.xyz` 这样的形式，不支持多级子域名，如 `bot.ue.gl-test.xyz` 。

# Upstream README:

---

[![readthedocs](https://readthedocs.org/projects/pip/badge/?version=latest&style=plastic)](https://lain-cli.readthedocs.io/en/latest/) [![CircleCI](https://circleci.com/gh/timfeirg/lain-cli.svg?style=svg)](https://circleci.com/gh/timfeirg/lain-cli) [![codecov](https://codecov.io/gh/timfeirg/lain-cli/branch/master/graph/badge.svg?token=A6153W38P4)](https://codecov.io/gh/timfeirg/lain-cli)

lain is a DevOps solution, but really, it just helps you with kubectl / helm / docker.

[![asciicast](https://asciinema.org/a/iLCiMoE4SDTyjcspXYfXGSkeO.svg)](https://asciinema.org/a/iLCiMoE4SDTyjcspXYfXGSkeO)

## Installation / Adoption

The recommended way to use lain is to [maintain an internal fork for your team](https://lain-cli.readthedocs.io/en/latest/dev.html#lain), this may be too much, you can still try out lain with the following steps:

- Install from PyPI: `pip install -U lain`
- Write cluster values, according to docs [here](https://lain-cli.readthedocs.io/en/latest/dev.html#cluster-values), and examples [here](https://github.com/timfeirg/lain-cli/tree/master/lain_cli/cluster_values), so that lain knows how to talk to your Kubernetes cluster
- Set `CLUSTER_VALUES_DIR` to the directory that contains all your cluster values
- Start using lain

## Links

- Documentation (Chinese): [lain-cli.readthedocs.io](https://lain-cli.readthedocs.io/en/latest/)

```

```
