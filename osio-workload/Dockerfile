FROM centos:7

RUN yum install -y epel-release && \
    yum install -y \
      bash \
      python36 \
      python36-pip \
      xz \
    && \
    yum update -y && \
    yum clean all && \
    rm -rf /var/cache/yum

#-- Include a kernel image for the untar operation
RUN curl -sSL https://cdn.kernel.org/pub/linux/kernel/v4.x/linux-4.1.51.tar.xz > /kernel.tar.xz && \
    chmod 644 /kernel.tar.xz

#-- /status is for a health marker file
#-- /data is where the fs to test should be mounted
RUN mkdir -p /data && chmod 777 /data && \
    mkdir -p /status && chmod 777 /status
VOLUME /data
VOLUME /status


#-- Set up the workload script
COPY entry.sh health.sh workload.py requirements.txt /
RUN chmod 755 /entry.sh /health.sh /workload.py && \
    pip3 install --upgrade -r requirements.txt
ENTRYPOINT ["/entry.sh"]

#-- Run as a non-root user
RUN useradd bench-runner
USER bench-runner:bench-runner

ARG builddate="(unknown)"
ARG version="(unknown)"
LABEL org.label-schema.build-date="${builddate}"
LABEL org.label-schema.description="OSIO workload simulation container"
LABEL org.label-schema.license="AGPL-3.0"
LABEL org.label-schema.name="osio-workload"
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.vcs-ref="${version}"
LABEL org.label-schema.vcs-url="https://github.com/JohnStrunk/ocs-monkey"
LABEL org.label-schema.vendor="John Strunk"
LABEL org.label-schema.version="${version}"
