package assessment.api;
import java.util.*;
public class Order {
 public String id,customerId,providerId,serviceId,status="PENDING";
 public int amountFen,version=0;
 public Map<String,Receipt> receipts=new LinkedHashMap<>();
 public static class Receipt {public String payload;public Map<String,Object> response; public Receipt(){} public Receipt(String p,Map<String,Object> r){payload=p;response=r;}}
 public Map<String,Object> view(){Map<String,Object> r=new LinkedHashMap<>();r.put("id",id);r.put("customerId",customerId);r.put("providerId",providerId);r.put("serviceId",serviceId);r.put("amountFen",amountFen);r.put("status",status);r.put("version",version);return r;}
}
