import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import {
  SafeAreaView,
  View,
  Text,
  Button,
  TextInput,
  FlatList,
  StyleSheet
} from "react-native";

export default function App() {
  const [name, setName] = useState("");
  const [students, setStudents] = useState([
    { id: "1", name: "Ada" },
    { id: "2", name: "Linus" }
  ]);

  function addStudent() {
    if (!name.trim()) return;

    setStudents([
      ...students,
      {
        id: Date.now().toString(),
        name: name.trim()
      }
    ]);

    setName("");
  }

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.title}>Expo React Native Lab</Text>

      <Text style={styles.description}>
        Questo esempio mostra componenti, stato, input, liste e hot reload.
      </Text>

      <View style={styles.card}>
        <TextInput
          style={styles.input}
          placeholder="Nome studente"
          value={name}
          onChangeText={setName}
        />

        <Button title="Aggiungi" onPress={addStudent} />
      </View>

      <FlatList
        data={students}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <View style={styles.row}>
            <Text style={styles.rowText}>{item.name}</Text>
          </View>
        )}
      />

      <StatusBar style="auto" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 24,
    backgroundColor: "#f5f5f5"
  },
  title: {
    fontSize: 28,
    fontWeight: "bold",
    marginBottom: 12
  },
  description: {
    fontSize: 16,
    marginBottom: 24
  },
  card: {
    backgroundColor: "white",
    padding: 16,
    borderRadius: 12,
    marginBottom: 20,
    gap: 12
  },
  input: {
    borderWidth: 1,
    borderColor: "#ccc",
    padding: 12,
    borderRadius: 8
  },
  row: {
    backgroundColor: "white",
    padding: 16,
    borderRadius: 8,
    marginBottom: 8
  },
  rowText: {
    fontSize: 18
  }
});