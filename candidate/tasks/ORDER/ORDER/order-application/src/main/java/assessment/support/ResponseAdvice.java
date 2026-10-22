package assessment.support;
import assessment.api.ResponseMsg;import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;
import org.springframework.core.MethodParameter;import org.springframework.http.*;import org.springframework.http.converter.HttpMessageConverter;import org.springframework.http.server.*;
import java.util.Map;
@ControllerAdvice public class ResponseAdvice implements ResponseBodyAdvice<Object>{
 public boolean supports(MethodParameter p,Class<? extends HttpMessageConverter<?>> c){return p.getContainingClass().getName().startsWith("assessment.controller.");}
 public Object beforeBodyWrite(Object value,MethodParameter p,MediaType type,Class<? extends HttpMessageConverter<?>> converter,ServerHttpRequest request,ServerHttpResponse response){if(request.getURI().getPath().equals("/healthz")||(value instanceof Map&&((Map)value).containsKey("code")))return value;return new ResponseMsg<>(value);}
}
