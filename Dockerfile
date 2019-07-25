FROM centos:7

RUN yum install -y epel-release && \
    yum install -y \
      bash \
      python36 \
      python36-pip \
    && \
    yum update -y && \
    yum clean all && \
    rm -rf /var/cache/yum

#-- Set up the workload script
COPY requirements.txt /
RUN pip3 install --upgrade -r requirements.txt

RUN curl -L https://mirror.openshift.com/pub/openshift-v4/clients/ocp/4.1.7/openshift-client-linux-4.1.7.tar.gz | tar xvzf -
COPY *.py oc_in_cluster.sh /
RUN chmod a+r /*.py && \
    chmod a+rx /oc_in_cluster.sh
ENTRYPOINT ["python3", "/runner.py"]

RUN mkdir -p /logs && chmod 777 /logs
VOLUME /logs

#-- Run as a non-root user
RUN useradd runner
USER runner:runner

ARG builddate="(unknown)"
ARG version="(unknown)"
LABEL org.label-schema.build-date="${builddate}"
LABEL org.label-schema.description="ocs-monkey workload simulator"
LABEL org.label-schema.license="AGPL-3.0"
LABEL org.label-schema.name="ocs-monkey-generator"
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.vcs-ref="${version}"
LABEL org.label-schema.vcs-url="https://github.com/JohnStrunk/ocs-monkey"
LABEL org.label-schema.vendor="John Strunk"
LABEL org.label-schema.version="${version}"
