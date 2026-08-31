package com.prominence.damage.boss;
import java.util.*;
public final class BossReportFormatter {
 public String format(String boss,String result,List<Contribution> players,List<Contribution> untraceable){
  StringBuilder b=new StringBuilder("[Boss Damage] ").append(boss).append(' ').append(result);double total=players.stream().mapToDouble(Contribution::damage).sum()+untraceable.stream().mapToDouble(Contribution::damage).sum();
  List<Contribution> sorted=new ArrayList<>(players);sorted.sort(Comparator.comparingDouble(Contribution::damage).reversed());int rank=1;for(Contribution c:sorted)b.append("\n").append(rank++).append(". ").append(c.name()).append(" — ").append(String.format(Locale.ROOT,"%.1f",c.damage())).append(" damage (").append(String.format(Locale.ROOT,"%.1f",total==0?0:c.damage()*100/total)).append("%)");
  for(Contribution c:untraceable)b.append("\nUntraceable: ").append(c.name()).append(" — ").append(String.format(Locale.ROOT,"%.1f",c.damage())).append(" damage");return b.toString();
 }
}
