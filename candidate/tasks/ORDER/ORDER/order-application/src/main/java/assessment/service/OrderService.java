package assessment.service;
    import assessment.api.*;import assessment.dao.OrderDao;import assessment.support.Problem;
    import org.springframework.stereotype.Service;import java.util.Map;
    @Service public class OrderService implements OrderOperations {
     private final OrderDao dao;public OrderService(OrderDao d){dao=d;}
     public Map<String,Object> transition(String id,String user,String action,String key,String note){
      // TODO: implement state transitions and idempotency using the existing DAO contract.
      throw new Problem(501,"NOT_IMPLEMENTED");
     }
    }
