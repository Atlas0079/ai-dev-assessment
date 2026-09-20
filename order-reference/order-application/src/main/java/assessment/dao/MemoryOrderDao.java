package assessment.dao;
import assessment.api.Order;
import org.springframework.stereotype.Repository;
import org.springframework.context.annotation.Profile;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
/** Trusted demo only. This profile is never sufficient to pass Mongo persistence checks. */
@Repository @Profile("demo") public class MemoryOrderDao implements OrderDao {
 private final Map<String,Order> data=new LinkedHashMap<>();private final ObjectMapper mapper=new ObjectMapper();
 private Order copy(Order o){return o==null?null:mapper.convertValue(o,Order.class);}
 public synchronized Order get(String id){return copy(data.get(id));}
 public synchronized void insert(Order o){data.put(o.id,copy(o));}
 public synchronized boolean replace(Order o,int v){if(data.get(o.id)==null||data.get(o.id).version!=v)return false;data.put(o.id,copy(o));return true;}
 public synchronized List<Order> all(){List<Order> list=new ArrayList<>();for(Order o:data.values())list.add(copy(o));return list;}
 public String mode(){return "memory-demo";}
}
