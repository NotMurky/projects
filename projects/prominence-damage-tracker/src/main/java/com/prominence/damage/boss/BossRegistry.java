package com.prominence.damage.boss;
import java.util.*;
public final class BossRegistry {
 private final Set<String> effective;
 public BossRegistry(Set<String> seeds,Set<String> tagged,Set<String> additions,Set<String> removals){Set<String>s=new TreeSet<>(seeds);s.addAll(tagged);s.addAll(additions);s.removeAll(removals);effective=Collections.unmodifiableSet(s);}
 public boolean isBoss(String id){return effective.contains(id);}
 public Set<String> all(){return effective;}
}
