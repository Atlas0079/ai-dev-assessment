package assessment.support;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import javax.servlet.http.HttpServletRequest;
public final class UserContext {
 private static final Map<String,String> TOKENS=new ConcurrentHashMap<>();
 public static String login(String name){if(!Arrays.asList("customer1","customer2","provider1","provider2").contains(name))throw new Problem(401,"UNKNOWN_ACCOUNT");String t=UUID.randomUUID().toString();TOKENS.put(t,name);return t;}
 public static String mustUser(HttpServletRequest r){String h=r.getHeader("Authorization");String u=h!=null&&h.startsWith("Bearer ")?TOKENS.get(h.substring(7)):null;if(u==null)throw new Problem(401,"UNAUTHENTICATED");return u;}
 public static boolean provider(String u){return u.startsWith("provider");}
}
