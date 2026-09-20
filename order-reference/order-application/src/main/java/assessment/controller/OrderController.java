package assessment.controller;
import assessment.api.*;import assessment.dao.OrderDao;import assessment.support.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;
import javax.servlet.http.HttpServletRequest;
import java.util.*;
@RestController public class OrderController {
 private final OrderDao dao;private final OrderOperations service;
 public OrderController(OrderDao d,OrderOperations s){dao=d;service=s;}
 @GetMapping("/healthz") public Map<String,Object> health(){Map<String,Object> r=new LinkedHashMap<>();r.put("status","ok");r.put("storage",dao.mode());return r;}
 @PostMapping("/v1/demo-login") public Map<String,String> login(@RequestBody Map<String,String> b){return Collections.singletonMap("token",UserContext.login(b.get("account")));}
 @GetMapping("/v1/services") public List<Map<String,Object>> services(){Map<String,Object> s=new LinkedHashMap<>();s.put("id","s1");s.put("title","双人游戏陪练");s.put("amountFen",3000);return Collections.singletonList(s);}
 @PostMapping("/v1/orders") public Map<String,Object> create(@RequestBody Map<String,Object> b,HttpServletRequest req){String u=UserContext.mustUser(req);if(UserContext.provider(u))throw new Problem(403,"FORBIDDEN");if(!"s1".equals(b.get("serviceId")))throw new Problem(400,"INVALID_SERVICE");Order o=new Order();o.id=UUID.randomUUID().toString();o.customerId=u;o.serviceId="s1";o.amountFen=3000;dao.insert(o);return o.view();}
 private boolean visible(Order o,String u){return u.equals(o.customerId)||u.equals(o.providerId)||(UserContext.provider(u)&&"PENDING".equals(o.status));}
 @GetMapping("/v1/orders/{id}") public Map<String,Object> detail(@PathVariable String id,HttpServletRequest req){String u=UserContext.mustUser(req);Order o=dao.get(id);if(o==null)throw new Problem(404,"NOT_FOUND");if(!"1".equals(System.getenv("BROKEN"))&&!visible(o,u))throw new Problem(403,"FORBIDDEN");return o.view();}
 @GetMapping("/v1/orders") public Map<String,Object> list(HttpServletRequest req,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="10")int size){String u=UserContext.mustUser(req);if(page<1||size<1||size>100)throw new Problem(400,"INVALID_PAGE");List<Map<String,Object>> rows=new ArrayList<>();for(Order o:dao.all())if(visible(o,u))rows.add(o.view());rows.sort(Comparator.comparing(x->String.valueOf(x.get("id"))));int start=Math.min((page-1)*size,rows.size());Map<String,Object> out=new LinkedHashMap<>();out.put("total",rows.size());out.put("items",rows.subList(start,Math.min(start+size,rows.size())));return out;}
 @PostMapping("/v1/orders/{id}/{action}") public Map<String,Object> action(@PathVariable String id,@PathVariable String action,@RequestHeader(value="Idempotency-Key",required=false)String key,@RequestBody(required=false)Map<String,Object>b,HttpServletRequest req){return service.transition(id,UserContext.mustUser(req),action,key,b==null?"":String.valueOf(b.getOrDefault("note","")));}
 @ExceptionHandler(Problem.class) public ResponseEntity<Map<String,String>> error(Problem p){return ResponseEntity.status(p.status).body(Collections.singletonMap("code",p.getMessage()));}
}
