package assessment.statemachine;
import assessment.api.Order;import assessment.support.Problem;import assessment.support.UserContext;
public final class Transitions {
 public static void apply(Order o,String user,String action){
  if("accept".equals(action)){if(!UserContext.provider(user))throw new Problem(403,"FORBIDDEN");if(!"PENDING".equals(o.status))throw new Problem(409,"INVALID_STATE");o.status="ACCEPTED";o.providerId=user;}
  else if("cancel".equals(action)){if(!user.equals(o.customerId))throw new Problem(403,"FORBIDDEN");if(!"PENDING".equals(o.status))throw new Problem(409,"INVALID_STATE");o.status="CANCELLED";}
  else if("complete".equals(action)){if(!UserContext.provider(user))throw new Problem(403,"FORBIDDEN");if(o.providerId!=null&&!user.equals(o.providerId))throw new Problem(403,"FORBIDDEN");if(!"ACCEPTED".equals(o.status))throw new Problem(409,"INVALID_STATE");o.status="COMPLETED";}
  else throw new Problem(404,"NOT_FOUND");
 }
}
