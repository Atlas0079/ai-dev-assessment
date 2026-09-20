package assessment.service;
import assessment.api.*;import assessment.dao.OrderDao;import assessment.support.*;import assessment.statemachine.Transitions;
import org.springframework.stereotype.Service;
import java.util.*;
@Service public class OrderService implements OrderOperations {
 private final OrderDao dao;public OrderService(OrderDao d){dao=d;}
 public Map<String,Object> transition(String id,String user,String action,String key,String note){
  if("1".equals(System.getenv("STARTER")))throw new Problem(501,"NOT_IMPLEMENTED");
  if(key==null||key.trim().isEmpty()||key.length()>100||note.length()>200)throw new Problem(400,"INVALID_INPUT");
  String receipt=Base64.getUrlEncoder().withoutPadding().encodeToString((user+":"+action+":"+key).getBytes(java.nio.charset.StandardCharsets.UTF_8));
  for(int attempt=0;attempt<5;attempt++){
   Order o=dao.get(id);if(o==null)throw new Problem(404,"NOT_FOUND");
   Order.Receipt old=o.receipts.get(receipt);
   if(old!=null){if(!old.payload.equals(note))throw new Problem(409,"IDEMPOTENCY_CONFLICT");return old.response;}
   int version=o.version;Transitions.apply(o,user,action);o.version++;
   Map<String,Object> out=o.view();o.receipts.put(receipt,new Order.Receipt(note,out));
   if(dao.replace(o,version))return out;
  }throw new Problem(409,"CONCURRENT_UPDATE");
 }
}
