package assessment.dao;
import assessment.api.Order;
import java.util.List;
public interface OrderDao {Order get(String id);void insert(Order o);boolean replace(Order o,int expectedVersion);List<Order> all();String mode();}
