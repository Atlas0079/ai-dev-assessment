ARG BASE_IMAGE
FROM ${BASE_IMAGE}
WORKDIR /source
COPY ORDER/ .
COPY maven-artifacts.lock /opt/maven-artifacts.lock
RUN mvn -B -q clean package -DskipTests && mvn -o -B -q clean package -DskipTests \
    && cd /root/.m2/repository \
    && find . -type f \( -name '*.jar' -o -name '*.pom' \) -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > /tmp/maven-actual.lock \
    && diff -u /opt/maven-artifacts.lock /tmp/maven-actual.lock \
    && rm -rf /source && mkdir /source
