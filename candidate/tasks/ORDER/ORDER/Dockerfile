FROM assessment-order-builder:fixed-v1 AS build
WORKDIR /source
COPY . .
RUN mvn -o -B -q package -DskipTests
FROM eclipse-temurin:8-jre@sha256:acfd157ba9dc5b7cbfd2bd2391bc206a6d23e6ddbba564eb89cf60e77de77831
WORKDIR /app
COPY --from=build /source/order-application/target/order-application-1.0.0.jar /app/app.jar
USER 10001
ENTRYPOINT ["java","-jar","/app/app.jar"]
