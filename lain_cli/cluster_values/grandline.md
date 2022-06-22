# GrandLine kubeconfig 配置说明

1. 安装 [aws-cli](https://aws.amazon.com/cli/) ，如:

```sh
brew install awscli
```

2. 用从管理员处获得的帐号密码登录 AWS ，获取 AWS Access Key ID 和 Secret Access Key ，并配置 awscli:

```sh
aws configure
```

`Default region name` 请填写 `us-west-2`

3. 配置 Docker 登录

```sh
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 625766999175.dkr.ecr.us-west-2.amazonaws.com
```

4. 生成 ~/.kube/kubeconfig-grandline:

```sh
aws eks update-kubeconfig --name prod --region us-west-2 --kubeconfig ~/.kube/kubeconfig-grandline
```

5. 生成 ~/.kube/kubeconfig-test:

```
cp ~/.kube/kubeconfig-grandline ~/.kube/kubeconfig-test
lain use --set-context test
```

## 注意

当前 grandline 集群使用 AWS ECR 作为 image registry ，但 ECR 要求需要先创建
repo 才能 push ，否则 push 会失败。因此在开启项目之后，`lain build` 之前，需要
先运行如下命令创建 repo:

```sh
aws ecr create-repository --repository-name {lain app name}
```
