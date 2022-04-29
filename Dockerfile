ARG BASE
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 LAIN_IGNORE_LINT="true" PS1="lain# "

ARG HELM_VERSION=3.8.0
ARG TRIVY_VERSION=0.23.0
ARG KUBECTL_VERSION=1.22.6

WORKDIR /srv/lain

RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata locales gnupg2 curl jq ca-certificates && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=en_US.UTF-8 && \
    curl -LO https://github.com/aquasecurity/trivy/releases/download/v$TRIVY_VERSION/trivy_${TRIVY_VERSION}_Linux-64bit.deb && \
    dpkg -i trivy_${TRIVY_VERSION}_Linux-64bit.deb && \
    curl -LO https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz && \
    tar -xvzf helm-v${HELM_VERSION}-linux-amd64.tar.gz && \
    mv linux-amd64/helm /usr/local/bin/helm && \
    chmod +x /usr/local/bin/helm && \
    rm -rf linux-amd64 *.tar.gz *.deb && \
    curl -LO https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    apt-get install -y \
    docker docker-compose mysql-client mytop libmysqlclient-dev redis-tools iputils-ping dnsutils \
    zip zsh fasd silversearcher-ag telnet rsync vim lsof tree openssh-client apache2-utils git git-lfs && \
    chsh -s /usr/bin/zsh root && \
    apt-get clean
ADD docker-image/.pip /root/.pip
COPY docker-image/git_askpass.sh /usr/local/bin/git_askpass.sh
ENV GIT_ASKPASS=/usr/local/bin/git_askpass.sh
COPY docker-image/.zshrc /root/.zshrc
COPY docker-image/requirements.txt /tmp/requirements.txt
COPY setup.py ./setup.py
COPY lain_cli ./lain_cli
RUN pip3 install -U -r /tmp/requirements.txt && \
    git init && \
    rm -rf /tmp/* .git

CMD ["bash"]
