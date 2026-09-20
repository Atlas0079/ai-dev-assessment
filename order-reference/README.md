# 模拟订单服务（内部参考答案）

独立编写，不含公司代码。Java 8 / Spring Boot 2.1.13 / Maven / MongoTemplate。

构建：`mvn -B package`。运行：`java -jar order-application/target/order-application-1.0.0.jar`。
变量：`PORT` 默认8080；`MONGO_URI` 默认 mongodb://localhost:27017/assessment。

`--spring.profiles.active=demo` 仅用于可信参考演示，使用内存DAO；不能据此宣称已通过MongoDB持久化或故障恢复评测。正式评测不得启用demo。

模拟账户 customer1/customer2/provider1/provider2。访问 `/` 操作，`/healthz` 检查存储模式。
订单状态与幂等回执在同一文档条件更新；不需要多文档事务或Redis锁。
