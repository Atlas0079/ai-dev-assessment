package assessment.api;
import java.util.Map;
public interface OrderOperations { Map<String,Object> transition(String orderId,String user,String action,String key,String note); }
