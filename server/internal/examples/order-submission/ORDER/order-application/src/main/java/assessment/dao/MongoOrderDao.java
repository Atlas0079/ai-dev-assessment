package assessment.dao;
import assessment.api.Order;
import org.springframework.stereotype.Repository;
import org.springframework.context.annotation.Profile;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.*;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.domain.Sort;
import javax.annotation.PostConstruct;
import java.util.*;
@Repository @Profile("!demo") public class MongoOrderDao implements OrderDao {
 private final MongoTemplate mongo;public MongoOrderDao(MongoTemplate m){mongo=m;}
 // Spring maps Order.id to MongoDB _id, which already has a unique index.
 public Order get(String id){return mongo.findOne(Query.query(Criteria.where("id").is(id)),Order.class,"orders");}
 public void insert(Order o){mongo.insert(o,"orders");}
 public boolean replace(Order o,int v){Update u=new Update().set("status",o.status).set("providerId",o.providerId).set("version",o.version).set("receipts",o.receipts);return mongo.updateFirst(Query.query(Criteria.where("id").is(o.id).and("version").is(v)),u,Order.class,"orders").getModifiedCount()==1;}
 public List<Order> all(){return mongo.findAll(Order.class,"orders");}public String mode(){return "mongodb";}
}
