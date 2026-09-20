FROM maven:3.9.9-eclipse-temurin-8 AS build
WORKDIR /source
COPY pom.xml .
COPY order-api order-api
COPY order-application order-application
RUN mvn -B -q package -DskipTests
FROM eclipse-temurin:8-jre
WORKDIR /app
COPY --from=build /source/order-application/target/order-application-1.0.0.jar /app/app.jar
USER 10001
ENTRYPOINT ["java","-jar","/app/app.jar"]
