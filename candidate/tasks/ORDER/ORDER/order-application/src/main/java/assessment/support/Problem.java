package assessment.support;
public class Problem extends RuntimeException {public final int status;public Problem(int s,String code){super(code);status=s;}}
