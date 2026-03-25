ARG BASE
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive LAIN_IGNORE_LINT="true" PS1="lain# "

ARG DOCKER_VERSION=29.3.0
ARG BUILDX_VERSION=0.32.1
ARG HELM_VERSION=3.12.2
ARG TRIVY_VERSION=0.23.0
ARG KUBECTL_VERSION=1.33.5

WORKDIR /srv/lain

RUN apt-get update && \
    echo "Install basic packages" && \
    apt-get install -y --no-install-recommends tzdata locales gnupg2 curl jq ca-certificates unzip && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    echo "Install kubectl" && \
    curl -LO https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    rm kubectl && \
    echo "Install helm" && \
    curl -LO https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz && \
    tar -xvzf helm-v${HELM_VERSION}-linux-amd64.tar.gz && \
    mv linux-amd64/helm /usr/local/bin/helm && \
    chmod +x /usr/local/bin/helm && \
    rm -rf linux-amd64 *.tar.gz && \
    echo "Install awscli" && \
    curl https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip && \
    unzip awscliv2.zip && \
    ./aws/install && \
    echo "Install trivy" && \
    curl -LO https://github.com/aquasecurity/trivy/releases/download/v$TRIVY_VERSION/trivy_${TRIVY_VERSION}_Linux-64bit.deb && \
    dpkg -i trivy_${TRIVY_VERSION}_Linux-64bit.deb && \
    rm *.deb && \
    echo "Install Docker CLI" && \
    curl -LO https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz && \
    tar -xzf docker-${DOCKER_VERSION}.tgz --strip-components=1 -C /usr/local/bin docker/docker && \
    rm docker-${DOCKER_VERSION}.tgz && \
    echo "Install Docker Buildx plugin" && \
    mkdir -p /usr/local/lib/docker/cli-plugins && \
    curl -Lo /usr/local/lib/docker/cli-plugins/docker-buildx \
        https://github.com/docker/buildx/releases/download/v${BUILDX_VERSION}/buildx-v${BUILDX_VERSION}.linux-amd64 && \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx && \
    echo "Install utility software" && \
    apt-get install -y \
    docker-compose mysql-client mytop libmysqlclient-dev redis-tools iputils-ping dnsutils \
    zip zsh fasd silversearcher-ag telnet rsync vim lsof tree openssh-client apache2-utils git git-lfs && \
    chsh -s /usr/bin/zsh root && \
    echo "Clean up" && \
    rm -rf /var/lib/apt/lists/*

ADD docker-image/.pip /root/.pip
COPY docker-image/git_askpass.sh /usr/local/bin/git_askpass.sh
ENV GIT_ASKPASS=/usr/local/bin/git_askpass.sh
COPY docker-image/.zshrc /root/.zshrc
COPY docker-image/requirements.txt /tmp/requirements.txt
COPY setup.py ./setup.py
COPY README.md ./README.md
COPY lain_cli ./lain_cli
RUN pip3 install -U -r /tmp/requirements.txt && \
    git init && \
    rm -rf /tmp/* .git

CMD ["bash"]
