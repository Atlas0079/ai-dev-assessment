package assessment.api;
/** Small original response envelope, not copied from the company utility library. */
public final class ResponseMsg<T> {public final int code=0;public final T data;public ResponseMsg(T value){data=value;}}
